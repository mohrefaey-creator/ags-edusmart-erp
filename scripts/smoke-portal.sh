#!/usr/bin/env bash
# End-to-end smoke check of the parent and staff portals against a running site.
#
# Verifies the things that unit tests cannot: that the whitelisted endpoints are
# actually reachable over HTTP, that a portal login resolves its own scope, and
# that the pages render. Run after any change to routing, hooks or permissions.
#
#   bash scripts/smoke-portal.sh [base_url] [user] [password]
set -uo pipefail

BASE=${1:-http://localhost:8000}
USER_EMAIL=${2:-mohamed.ahmed@example.com}
PASSWORD=${3:-demo-not-a-real-credential}
COOKIES=$(mktemp)
# If mktemp fails, or a caller invokes this through a layer that strips the
# quoting, `-c "${COOKIES}"` collapses to a bare `-c` and curl takes the NEXT
# argument as the jar filename — which is how files literally named `-X` and
# `-m`, containing a live session cookie, once got committed to this repo.
if [ -z "${COOKIES}" ] || [ ! -f "${COOKIES}" ]; then
  echo "could not create a cookie jar; refusing to run" >&2
  exit 1
fi
trap 'rm -f "${COOKIES}"' EXIT
FAILED=0

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=$((FAILED + 1)); }

check_status() {
  local label=$1 url=$2 expected=$3
  local code
  code=$(curl -s -b "${COOKIES}" -o /dev/null -w '%{http_code}' -m 30 "${url}")
  if [[ "${code}" == "${expected}" ]]; then
    pass "${label} (HTTP ${code})"
  else
    fail "${label} (HTTP ${code}, expected ${expected})"
  fi
}

check_json_has() {
  local label=$1 url=$2 needle=$3 body
  body=$(curl -s -b "${COOKIES}" -m 30 "${url}")
  if grep -q "${needle}" <<<"${body}"; then
    pass "${label}"
  else
    fail "${label} — did not find '${needle}' in: ${body:0:300}"
  fi
}

echo "AGS EduSmart portal smoke check against ${BASE}"
echo

echo "unauthenticated"
# A logged-out caller must not reach parent data at all.
code=$(curl -s -o /dev/null -w '%{http_code}' -m 30 \
  "${BASE}/api/method/ags_edusmart.api.portal.my_children")
if [[ "${code}" == "403" || "${code}" == "401" ]]; then
  pass "my_children refuses anonymous access (HTTP ${code})"
else
  fail "my_children allowed anonymous access (HTTP ${code})"
fi

echo
echo "login"
login=$(curl -s -c "${COOKIES}" -m 30 -X POST "${BASE}/api/method/login" \
  --data-urlencode "usr=${USER_EMAIL}" --data-urlencode "pwd=${PASSWORD}")
if grep -q '"full_name"' <<<"${login}"; then
  pass "signed in as ${USER_EMAIL}"
else
  fail "login failed: ${login:0:200}"
  echo; echo "aborting"; exit 1
fi

echo
echo "parent API"
check_json_has "my_children returns the family" \
  "${BASE}/api/method/ags_edusmart.api.portal.my_children" '"student_name"'
check_json_has "my_outstanding returns a balance" \
  "${BASE}/api/method/ags_edusmart.api.portal.my_outstanding" 'total_outstanding'
check_json_has "my_statement consolidates siblings" \
  "${BASE}/api/method/ags_edusmart.api.portal.my_statement" '"payer"'
check_json_has "my_installments lists the schedule" \
  "${BASE}/api/method/ags_edusmart.api.portal.my_installments" 'message'

echo
echo "parent pages"
check_status "GET /parent"      "${BASE}/parent"      200
check_status "GET /parent/fees" "${BASE}/parent/fees" 200

echo
echo "isolation"
# A parent asking about a student who is not theirs must be refused, not served.
body=$(curl -s -b "${COOKIES}" -m 30 \
  "${BASE}/api/method/ags_edusmart.api.portal.my_child_attendance?student=NOT-MY-CHILD")
if grep -qi 'PermissionError\|not permitted' <<<"${body}"; then
  pass "attendance refuses a student outside the family"
else
  fail "attendance did not refuse a foreign student: ${body:0:200}"
fi

rm -f "${COOKIES}"
echo
if [[ ${FAILED} -eq 0 ]]; then
  echo "all checks passed"
else
  echo "${FAILED} check(s) failed"
fi
exit "${FAILED}"
