#!/usr/bin/env bash
# Complete Frappe's first-run setup wizard from the command line.
#
#   cd deploy/compose
#   COMPANY_NAME="AGS Education Group" bash complete-setup.sh
#
# Frappe holds every logged-in user at /desk/setup-wizard until the wizard is
# completed, which makes a fresh site look like "login does nothing". The
# wizard is four screens of clicking; this is the same call it makes at the
# end, from the terminal, so first-day setup is one command on the VM and a
# reviewer is never left staring at a language dropdown.
#
# It creates the Company — the operation that used to fail on a fresh site
# with `Could not find Warehouse Type: Transit` before the fixture fix. If this
# succeeds, that fix is proven where it matters.
#
# Idempotent: refuses to run if setup is already complete.
set -euo pipefail

cd "$(dirname "$0")"
[ -f .env ] || { echo "no .env here — run from deploy/compose after setup" >&2; exit 1; }
SITE=$(grep -E '^SITE_NAME=' .env | cut -d= -f2)

# Evaluation defaults. Override any of them in the environment.
COMPANY_NAME=${COMPANY_NAME:-AGS Education Group}
COMPANY_ABBR=${COMPANY_ABBR:-AGS}
COUNTRY=${COUNTRY:-Saudi Arabia}
TIMEZONE=${TIMEZONE:-Asia/Riyadh}
CURRENCY=${CURRENCY:-SAR}
LANGUAGE=${LANGUAGE:-en}
FY_START=${FY_START:-$(date +%Y)-01-01}
FY_END=${FY_END:-$(date +%Y)-12-31}
# The wizard's "your account" screen creates a System Manager user. Placeholder
# identity here; log in as Administrator with ADMIN_PASSWORD from .env.
FULL_NAME=${FULL_NAME:-AGS Administrator}
USER_EMAIL=${USER_EMAIL:-admin@ags.local}
USER_PASSWORD=${USER_PASSWORD:-$(grep -E '^ADMIN_PASSWORD=' .env | cut -d= -f2)}

COMPOSE="docker compose -f compose.yaml"
[ -f compose.local.yaml ] && ${COMPOSE} -f compose.local.yaml ps web >/dev/null 2>&1 \
  && COMPOSE="${COMPOSE} -f compose.local.yaml"

# Idempotent: setup_complete is 1 once the wizard has run, by any route.
done=$(${COMPOSE} exec -T web bench --site "${SITE}" execute frappe.db.get_single_value   --kwargs "{'doctype': 'System Settings', 'fieldname': 'setup_complete'}" 2>/dev/null | tr -d '[:space:]')
if [ "${done}" = "1" ]; then
  echo "setup already complete on ${SITE} — nothing to do"
  exit 0
fi

echo "site     : ${SITE}"
echo "company  : ${COMPANY_NAME} (${COMPANY_ABBR}), ${COUNTRY}, ${CURRENCY}, FY ${FY_START}..${FY_END}"

${COMPOSE} exec -T web bench --site "${SITE}" execute \
  frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
  --kwargs "{'args': {
    'language': '${LANGUAGE}',
    'country': '${COUNTRY}',
    'timezone': '${TIMEZONE}',
    'currency': '${CURRENCY}',
    'full_name': '${FULL_NAME}',
    'email': '${USER_EMAIL}',
    'password': '${USER_PASSWORD}',
    'company_name': '${COMPANY_NAME}',
    'company_abbr': '${COMPANY_ABBR}',
    'fy_start_date': '${FY_START}',
    'fy_end_date': '${FY_END}',
    'chart_of_accounts': 'Standard',
    'setup_demo': 0
  }}"

echo
echo "== verifying =="
${COMPOSE} exec -T web bench --site "${SITE}" execute frappe.client.get_list \
  --kwargs "{'doctype': 'Company', 'fields': ['name', 'abbr', 'country', 'default_currency']}"
${COMPOSE} exec -T web bench --site "${SITE}" execute frappe.db.get_single_value \
  --kwargs "{'doctype': 'System Settings', 'fieldname': 'setup_complete'}"
echo "setup_complete above should be 1"
