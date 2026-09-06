#!/usr/bin/env bash
# Which Python base image can actually run this stack?
#
# Frappe 16 pins `requires-python = ">=3.14,<3.15"` — an unusually tight range.
# Picking a base by habit (python:3.12-slim) produces a build that fails deep
# inside `bench init` with a uv resolver message, minutes in.
set -uo pipefail

CANDIDATES=(
  "python:3.14-slim-trixie"
  "python:3.14-slim-bookworm"
  "python:3.14-slim"
  "python:3.14"
)

echo "Frappe 16 requires Python >=3.14,<3.15"
echo
for tag in "${CANDIDATES[@]}"; do
  if docker manifest inspect "${tag}" >/dev/null 2>&1; then
    printf '  \033[32mAVAILABLE\033[0m  %s\n' "${tag}"
  else
    printf '  missing    %s\n' "${tag}"
  fi
done
