#!/usr/bin/env bash
# Prove the built image is actually usable.
#
#   sudo bash scripts/verify-image.sh [tag]
#
# "docker build succeeded" is a weak claim: the image can build cleanly and
# still be missing an app, carry the wrong Python, or have failed its asset
# build. These checks run inside the image and fail loudly.
set -uo pipefail

TAG=${1:-ags/edusmart-erp:local}
PASS=0
FAIL=0

ok()  { printf '   \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '   \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found — run: sudo bash scripts/build-image.sh" >&2; exit 1; }

printf '\n\033[1mVerifying %s\033[0m\n\n' "${TAG}"

run() { docker run --rm --entrypoint /bin/bash "${TAG}" -c "$1" 2>&1; }

# --------------------------------------------------------------- interpreters
py=$(run 'python --version' | head -1)
case "${py}" in
  *3.14*) ok "Python is 3.14 (${py}) — frappe 16 pins >=3.14,<3.15" ;;
  *)      bad "wrong Python: ${py} — frappe 16 requires >=3.14,<3.15" ;;
esac

node=$(run 'node --version' | head -1)
major=$(printf '%s' "${node}" | tr -d 'v' | cut -d. -f1)
if [ "${major:-0}" -ge 24 ] 2>/dev/null; then
  ok "Node is ${node} — frappe engines require >=24"
else
  bad "Node is ${node} — frappe engines require >=24 (socketio fails at runtime)"
fi

# ---------------------------------------------------------------------- apps
apps=$(run 'ls apps' | tr -d '\r' | tr '\n' ' ')
missing=""
for app in frappe erpnext payments hrms education ags_edusmart; do
  case " ${apps} " in *" ${app} "*) ;; *) missing="${missing} ${app}" ;; esac
done
if [ -z "${missing}" ]; then
  ok "all apps present:${apps}"
else
  bad "missing app(s):${missing}"
fi

# sites/apps.txt is checked separately from `ls apps`, because the two can
# disagree in a way that builds cleanly and then fails at the first `frappe.init`.
# `bench get-app` writes the file without a trailing newline, so appending an app
# to it splices onto the last entry: `payments` + `ags_edusmart` became the single
# token `paymentsags_edusmart`, and the asset build died importing a module by
# that name. Every entry must be a directory under apps/.
appstxt=$(run 'cat sites/apps.txt' | tr -d '\r')
bogus=""
for entry in ${appstxt}; do
  case " ${apps} " in *" ${entry} "*) ;; *) bogus="${bogus} ${entry}" ;; esac
done
if [ -n "${bogus}" ]; then
  bad "sites/apps.txt names app(s) that do not exist:${bogus} (spliced line?)"
elif [ -z "${appstxt}" ]; then
  bad "sites/apps.txt is empty"
else
  ok "sites/apps.txt is one app per line, all resolvable"
fi

# An app can be on disk and still not importable — a failed editable install
# looks exactly like a healthy one from `ls`.
imports=$(run 'env/bin/python -c "import frappe, erpnext, payments, hrms, education, ags_edusmart; print(ags_edusmart.__version__)"')
case "${imports}" in
  *Error*|*Traceback*) bad "apps do not import: $(printf '%s' "${imports}" | tail -2)" ;;
  "") bad "import check produced no output" ;;
  *) ok "all apps import (ags_edusmart ${imports})" ;;
esac

# --------------------------------------------------------------------- assets
assets=$(run 'ls sites/assets 2>/dev/null | wc -l')
if [ "${assets:-0}" -gt 1 ] 2>/dev/null; then
  ok "asset bundles built (${assets} entries under sites/assets)"
else
  bad "sites/assets looks empty — 'bench build --production' did not run"
fi

# The AGS bundles specifically: a build can succeed for the upstream apps and
# silently skip a custom app's bundles.
ags_assets=$(run 'ls sites/assets/ags_edusmart/dist 2>/dev/null | tr "\n" " "')
case "${ags_assets}" in
  *css*|*js*) ok "AGS bundles present: ${ags_assets}" ;;
  *) bad "no AGS asset bundles under sites/assets/ags_edusmart/dist" ;;
esac

# -------------------------------------------------------------------- tooling
pdf=$(run 'which wkhtmltopdf')
case "${pdf}" in
  */wkhtmltopdf) ok "wkhtmltopdf present (invoice and payslip rendering)" ;;
  *) bad "wkhtmltopdf missing — invoices and payslips will not render" ;;
esac

fonts=$(run 'fc-list 2>/dev/null | grep -ci noto || ls /usr/share/fonts/truetype 2>/dev/null | grep -ci noto')
if [ "${fonts:-0}" -gt 0 ] 2>/dev/null; then
  ok "Noto fonts present (Arabic shaping in generated PDFs)"
else
  bad "no Noto fonts — Arabic invoices will print boxes"
fi

# ---------------------------------------------------------------- roles
# Every role the entrypoint dispatches, not just the one that happens to work.
#
# The entrypoint hardcoded env/bin/bench, which does not exist — bench is
# installed with `pip install --user` and lives in ~/.local/bin, while gunicorn
# is a frappe dependency in the bench virtualenv. The web role worked and the
# other four did not, and nothing here noticed because these checks only ever
# looked at imports and assets. A container image whose entrypoint cannot find
# its own binary is not a working image.
for cmd in bench gunicorn node; do
  found=$(run "command -v ${cmd} || true")
  case "${found}" in
    */"${cmd}") ok "${cmd} resolves on PATH (${found})" ;;
    *) bad "${cmd} is not on PATH — the roles that use it cannot start" ;;
  esac
done

# The dispatch itself: `bench --version` exercises the same lookup the worker,
# scheduler and migrate roles make, without needing a database.
bench_version=$(run 'bench --version 2>&1 | head -1')
case "${bench_version}" in
  *[0-9]*) ok "bench runs (${bench_version})" ;;
  *) bad "bench does not run: ${bench_version}" ;;
esac

# ----------------------------------------------------------------- entrypoint
entry=$(docker run --rm --entrypoint /bin/bash "${TAG}" -c 'head -1 /usr/local/bin/entrypoint.sh' 2>&1)
case "${entry}" in
  *bash*) ok "entrypoint installed" ;;
  *) bad "entrypoint missing or unreadable" ;;
esac

user=$(run 'id -un')
if [ "${user}" = "frappe" ]; then
  ok "runs as non-root (${user})"
else
  bad "image runs as ${user} — should be the unprivileged frappe user"
fi

size=$(docker images "${TAG}" --format '{{.Size}}')
printf '\n   image size: %s\n' "${size}"

printf '\n   passed %s / failed %s\n\n' "${PASS}" "${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
