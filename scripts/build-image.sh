#!/usr/bin/env bash
# Build the application container image.
#
#   sudo bash scripts/build-image.sh [tag]
#
# Writes the full build log to a file and reports the real exit status.
# Piping `docker build` into `tail` swallows its exit code unless pipefail is
# set — a failed build then looks like a successful one, which is exactly how
# the first attempt here appeared to pass while `bench init` had aborted.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=${1:-ags/edusmart-erp:local}
LOG=${LOG:-/tmp/ags-image-build.log}

command -v docker >/dev/null 2>&1 || {
  echo "docker not installed — run: sudo bash scripts/start-docker.sh" >&2; exit 1; }
docker info >/dev/null 2>&1 || {
  echo "docker daemon not running — run: sudo bash scripts/start-docker.sh" >&2; exit 1; }

cd "${REPO_ROOT}"

echo "building ${TAG}"
echo "log: ${LOG}"
echo

set -o pipefail
docker build \
  -f infra/docker/Dockerfile \
  -t "${TAG}" \
  . 2>&1 | tee "${LOG}" | grep -E '^(Step|Successfully|ERROR|error)'
status=${PIPESTATUS[0]}

echo
if [ "${status}" -ne 0 ]; then
  echo "BUILD FAILED (exit ${status}). Last 30 log lines:" >&2
  tail -30 "${LOG}" >&2
  exit "${status}"
fi

echo "built ${TAG}"
docker images "${TAG%%:*}" --format '  {{.Repository}}:{{.Tag}}  {{.Size}}'
