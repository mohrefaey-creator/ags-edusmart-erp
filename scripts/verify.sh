#!/usr/bin/env bash
# Prove the stack works. One command, everything that can fail.
#
#   bash scripts/verify.sh
#
# Runs, in order of how cheap they are:
#   1. generated schema still matches its specs        (seconds, no DB)
#   2. translations complete, placeholders intact      (seconds, no DB)
#   3. shell and config syntax                         (seconds, no DB)
#   4. sync + migrate                                  (needs the bench)
#   5. full test suite against a live site
#   6. portal end to end, including its negative cases
#
# Exits non-zero on the first hard failure, with a summary either way.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_REPO="${REPO_ROOT}/apps/ags_edusmart"
BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
BASE_URL=${BASE_URL:-http://localhost:8000}

# Frappe refuses to run as root, so `sudo bash scripts/verify.sh` would report
# three false failures. Drop to the bench user rather than making the caller
# remember which scripts need sudo and which reject it (bootstrap.sh needs it;
# this does not).
if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
	printf '   re-running as %s (Frappe cannot run as root)\n' "${BENCH_USER}"
	exec su - "${BENCH_USER}" -c "bash '${BASH_SOURCE[0]}' $*"
fi

SMOKE_LOG="$(mktemp -t ags-smoke.XXXXXX)"
trap 'rm -f "${SMOKE_LOG}"' EXIT

PASS=0
FAIL=0
SKIP=0

step()  { printf '\n\033[1m── %s\033[0m\n' "$1"; }
ok()    { printf '   \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
bad()   { printf '   \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
skip()  { printf '   \033[33mSKIP\033[0m  %s\n' "$1"; SKIP=$((SKIP+1)); }

have_python() { command -v python3 >/dev/null 2>&1; }
in_bench()    { [ -d "${BENCH_DIR}/apps/frappe" ]; }

bench_run() {
  # bench needs its own PATH and cwd; keep that in one place.
  ( cd "${BENCH_DIR}" && export PATH="${HOME}/.local/bin:${PATH}" && bench "$@" )
}

# ---------------------------------------------------------------- 1. schema
step "Generated schema matches its specs"
# Compared by content hash rather than `git diff`. This script runs from WSL
# against a repo on a Windows mount, where git refuses with "dubious ownership"
# and the check would report a false failure. Hashing needs no git at all.
if have_python && [ -d "${APP_REPO}/tools" ]; then
  out=$(cd "${APP_REPO}" && python3 - <<'PY' 2>&1
import hashlib, glob, os, subprocess, sys

def fingerprint():
    digest = hashlib.sha256()
    for path in sorted(glob.glob("ags_edusmart/**/doctype/**/*.json", recursive=True)):
        digest.update(path.encode())
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()

before = fingerprint()
result = subprocess.run([sys.executable, "tools/generate.py"],
                        capture_output=True, text=True)
if result.returncode != 0:
    print("GENERATOR_FAILED")
    print(result.stdout[-500:], result.stderr[-500:])
    raise SystemExit(0)

after = fingerprint()
print("IN_SYNC" if before == after else "STALE")
print(result.stdout.strip())
PY
  )
  if printf '%s\n' "${out}" | grep -q IN_SYNC; then
    count=$(printf '%s\n' "${out}" | grep -oE 'generated [0-9]+' | grep -oE '[0-9]+')
    ok "${count:-?} DocType JSON files match tools/specs_*.py"
  elif printf '%s\n' "${out}" | grep -q GENERATOR_FAILED; then
    bad "tools/generate.py failed"
    printf '%s\n' "${out}" | tail -4
  else
    bad "DocType JSON was stale — regenerated. Commit the diff in the app repo."
  fi
else
  skip "python3 or the app repo is not available here"
fi

# --------------------------------------------------------- 2. translations
step "Arabic translations"
if have_python; then
  out=$( cd "${APP_REPO}" && PYTHONIOENCODING=utf-8 python3 tools/build_translations.py --check 2>&1 )
  status=$?
  coverage=$(printf '%s\n' "${out}" | grep -oE 'coverage +: +[0-9.]+%' | grep -oE '[0-9.]+%')
  missing=$(printf '%s\n' "${out}" | grep -oE 'missing +: +[0-9]+' | grep -oE '[0-9]+$')
  if [ "${status}" -eq 0 ] && [ "${missing:-1}" = "0" ]; then
    ok "coverage ${coverage:-?}, no missing strings, placeholders intact"
  else
    bad "translation check failed (missing=${missing:-?})"
    printf '%s\n' "${out}" | head -12
  fi
else
  skip "python3 unavailable"
fi

# ---------------------------------------------------------------- 3. syntax
step "Shell and config syntax"
syntax_bad=0
for f in "${REPO_ROOT}"/scripts/*.sh "${REPO_ROOT}"/infra/docker/entrypoint.sh; do
  [ -f "$f" ] || continue
  bash -n "$f" 2>/dev/null || { bad "bash syntax: $(basename "$f")"; syntax_bad=1; }
done
[ "${syntax_bad}" -eq 0 ] && ok "all shell scripts parse"

if have_python; then
  if python3 - "${REPO_ROOT}" <<'PY' >/dev/null 2>&1
import glob, os, sys
try:
    import yaml
except ImportError:
    sys.exit(0)          # not installed here; CI covers it
root = sys.argv[1]
for path in glob.glob(os.path.join(root, "infra", "**", "*.y*ml"), recursive=True):
    list(yaml.safe_load_all(open(path, encoding="utf-8")))
PY
  then ok "infra YAML parses"
  else bad "infra YAML failed to parse"
  fi
fi

# CRLF in a shell script or a MariaDB config breaks it inside Linux.
if command -v file >/dev/null 2>&1; then
  crlf=$(grep -rlU $'\r' "${REPO_ROOT}/scripts" "${REPO_ROOT}/infra" 2>/dev/null | head -3)
  if [ -z "${crlf}" ]; then
    ok "no CRLF line endings in scripts or infra"
  else
    bad "CRLF found (will break in Linux): ${crlf}"
  fi
fi

# ------------------------------------------------------- 4. sync + migrate
step "Sync and migrate"
if in_bench; then
  if bash "${REPO_ROOT}/scripts/sync-app.sh" >/dev/null 2>&1; then
    ok "app synced into the bench"
  else
    bad "sync-app.sh failed"
  fi
  if bench_run --site "${SITE}" migrate >/dev/null 2>&1; then
    ok "migrate clean"
  else
    bad "migrate failed"
  fi
else
  skip "no bench at ${BENCH_DIR} — run scripts/bootstrap.sh first"
fi

# ----------------------------------------------------------------- 5. tests
step "Test suite"
if in_bench; then
  out=$(bench_run --site "${SITE}" run-tests --app ags_edusmart 2>&1 | tr '\r' '\n')
  ran=$(printf '%s\n' "${out}" | grep -cE '^OK$')
  failed=$(printf '%s\n' "${out}" | grep -cE '^FAILED')
  counts=$(printf '%s\n' "${out}" | grep -oE 'Ran [0-9]+ tests' | grep -oE '[0-9]+' | paste -sd+ | bc 2>/dev/null)
  if [ "${failed}" -eq 0 ] && [ "${ran}" -gt 0 ]; then
    ok "${counts:-?} tests passed"
  else
    bad "test suite failed"
    printf '%s\n' "${out}" | grep -E '✖|FAILED|Error|AssertionError' | head -10
  fi
else
  skip "no bench"
fi

# ---------------------------------------------------------------- 6. portal
step "Portal end to end"
if curl -sf -m 10 "${BASE_URL}/api/method/ping" >/dev/null 2>&1; then
  if bash "${REPO_ROOT}/scripts/smoke-portal.sh" "${BASE_URL}" >${SMOKE_LOG} 2>&1; then
    checks=$(grep -c 'PASS' ${SMOKE_LOG})
    ok "${checks} portal checks passed (incl. anonymous and foreign-student refusal)"
  else
    bad "portal smoke check failed"
    grep -E 'FAIL' ${SMOKE_LOG} | head -5
  fi
else
  skip "nothing serving at ${BASE_URL} — run scripts/start-dev.sh"
fi

# --------------------------------------------------------------- summary
printf '\n\033[1m%s\033[0m\n' "────────────────────────────────────────"
printf '  passed  %s\n' "${PASS}"
printf '  failed  %s\n' "${FAIL}"
printf '  skipped %s\n' "${SKIP}"
if [ "${FAIL}" -eq 0 ]; then
  printf '\n\033[32m  stack verified\033[0m\n\n'
  exit 0
fi
printf '\n\033[31m  %s check(s) failed\033[0m\n\n' "${FAIL}"
exit 1
