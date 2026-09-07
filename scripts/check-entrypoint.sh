#!/usr/bin/env bash
# Which bench path does the built image's entrypoint actually use?
#
#   sudo bash scripts/check-entrypoint.sh [tag]
#
# The entrypoint used to call env/bin/bench, which does not exist in the image —
# bench is installed with `pip install --user` into ~/.local/bin. Only the web
# role survived that, because gunicorn genuinely is in env/bin. This answers
# "did the rebuild actually pick up the fix" without reading a build log that
# WSL may have cleared out of /tmp.
set -uo pipefail

TAG=${1:-ags/edusmart-erp:local}

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found" >&2; exit 1; }

out=$(docker run --rm --entrypoint /bin/bash "${TAG}" -c '
  printf "built_at_role_lines:\n"
  grep -nE "exec (bench|gunicorn|env/bin/[a-z]+)" /usr/local/bin/entrypoint.sh
  printf "bench_on_path: "
  command -v bench || echo NONE
' 2>&1)

printf '%s\n' "${out}"

if printf '%s\n' "${out}" | grep -q 'env/bin/bench'; then
  echo
  echo "STALE: this image still calls env/bin/bench — the rebuild did not land."
  exit 1
fi
echo
echo "OK: entrypoint resolves bench from PATH."
