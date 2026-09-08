#!/usr/bin/env bash
# Runs INSIDE the container. Executes the ags_edusmart suite.
# Expects: SITE
set -uo pipefail
cd /home/frappe/frappe-bench
bench --site "${SITE}" set-config allow_tests true >/dev/null 2>&1 || true
bench --site "${SITE}" run-tests --app ags_edusmart
