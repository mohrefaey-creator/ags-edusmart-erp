#!/usr/bin/env bash
# Re-apply the runtime-stage deltas on top of an already-built image.
#
#   sudo bash scripts/patch-runtime-image.sh
#
# WHY THIS EXISTS, AND WHEN NOT TO USE IT
#
# infra/docker/Dockerfile's late steps are cheap, but step 30 is
# `COPY --from=builder /home/frappe /home/frappe` — about 2 GB. With the build
# cache cold that step re-runs, and on a 4 GB WSL VM whose host is down to a few
# hundred MB it does not merely fail, it takes the VM down. Three attempts, three
# crashes, for a one-file change.
#
# So this re-applies the same runtime-stage changes a full build would, without
# redoing the expensive one. Keep it in step with the Dockerfile: today that is
# the git package and the entrypoint. It is a development convenience on a memory-constrained
# machine. The canonical artefact is what `scripts/build-image.sh` produces from
# infra/docker/Dockerfile, and that is what CI and any release must use — an
# image built this way has a different provenance from the one the Dockerfile
# describes, even when the bytes agree.
#
# Run scripts/verify-image.sh afterwards either way: the point of the fix is
# that the entrypoint can find its own binary, and that is what verify checks.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=${BASE:-ags/edusmart-erp:local}
TAG=${TAG:-ags/edusmart-erp:local}

docker image inspect "${BASE}" >/dev/null 2>&1 || {
  echo "base image ${BASE} not found — run scripts/build-image.sh first" >&2
  exit 1
}

work=$(mktemp -d)
trap 'rm -rf "${work}"' EXIT
cp "${REPO_ROOT}/infra/docker/entrypoint.sh" "${work}/entrypoint.sh"

# Mirrors the runtime stage of infra/docker/Dockerfile. Keep in step with it.
#
# git is here for the same reason it is in the Dockerfile: bench imports
# GitPython at module level, and GitPython raises on import when the git binary
# is missing, so every bench-based role fails before it starts.
cat > "${work}/Dockerfile" <<EOF
FROM ${BASE}
USER root
RUN apt-get update  && apt-get install -y --no-install-recommends git  && rm -rf /var/lib/apt/lists/*
COPY --chown=frappe:frappe entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
USER frappe
EOF

echo "re-applying runtime deltas on ${BASE}"
docker build -t "${TAG}" "${work}" || { echo "build failed" >&2; exit 1; }

echo
bash "${REPO_ROOT}/scripts/check-entrypoint.sh" "${TAG}"
