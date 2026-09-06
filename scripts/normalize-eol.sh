#!/usr/bin/env bash
# Force LF on everything that Linux executes.
#
#   sudo bash scripts/normalize-eol.sh          # report
#   sudo bash scripts/normalize-eol.sh --fix    # rewrite
#
# .gitattributes already forces LF *in the repository*, but the working tree on
# this machine is edited from Windows and executed from WSL, and WSL reads the
# files off /mnt/c directly rather than through git. A CRLF shell script fails
# in a way that never mentions line endings:
#
#     set: pipefail: invalid option name
#     $'\r': command not found
#     syntax error near unexpected token `$'{\r''
#
# Any editor or tool that writes with platform newlines reintroduces this, so
# this is a check worth being able to run, not a one-time cleanup.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

cd "${REPO_ROOT}" || exit 1

found=0
while IFS= read -r file; do
  # -U keeps grep from stripping CR before matching on some platforms.
  if grep -qU $'\r' "${file}" 2>/dev/null; then
    found=$((found + 1))
    if [ "${FIX}" -eq 1 ]; then
      sed -i 's/\r$//' "${file}"
      echo "  fixed   ${file}"
    else
      echo "  CRLF    ${file}"
    fi
  fi
done < <(find . -type f \
           \( -name '*.sh' -o -name '*.js' -o -name '*.py' \) \
           -not -path './.git/*' \
           -not -path './apps/*/.git/*' \
           | sort)

if [ "${found}" -eq 0 ]; then
  echo "  all executable files are LF"
  exit 0
fi

if [ "${FIX}" -eq 1 ]; then
  echo "  normalised ${found} file(s)"
  exit 0
fi

echo "  ${found} file(s) have CRLF — re-run with --fix"
exit 1
