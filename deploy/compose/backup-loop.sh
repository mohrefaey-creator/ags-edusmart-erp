#!/usr/bin/env bash
# Nightly backup for the single-VM deployment.
#
# A sleep loop in a container rather than cron on the host, so the whole
# deployment is one `docker compose up` with nothing to remember to install on
# the VM — and so the backup runs with exactly the image, volume and
# credentials the application uses. The trade is that restarting this container
# resets the timer to the next scheduled time; for a nightly job that is fine.
#
# BACKUP_AT_UTC is UTC, deliberately. 22:15 UTC is 01:15 in Riyadh: clear of the
# 07:00 peak and after the nightly reminder and ageing passes have settled.
set -uo pipefail

AT=${BACKUP_AT_UTC:-22:15}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
BACKUP_DIR="/home/frappe/frappe-bench/sites/${SITE_NAME}/private/backups"

echo "[backup] nightly at ${AT} UTC, keeping ${KEEP_DAYS} days"

while true; do
  now=$(date -u +%s)
  next=$(date -u -d "today ${AT}" +%s 2>/dev/null) || {
    echo "[backup] BACKUP_AT_UTC='${AT}' is not a time date(1) understands" >&2
    exit 1
  }
  [ "${next}" -le "${now}" ] && next=$(date -u -d "tomorrow ${AT}" +%s)

  echo "[backup] next run in $(( (next - now) / 60 )) minutes"
  sleep $(( next - now ))

  echo "[backup] starting $(date -u +%FT%TZ)"
  # The image's own backup role, so the site name comes from SITE_NAME exactly
  # as it does for every other role rather than being repeated here.
  if /usr/local/bin/entrypoint.sh backup --with-files; then
    echo "[backup] completed $(date -u +%FT%TZ)"
  else
    # Loud, and does not exit: a failed backup must not stop tomorrow's from
    # being attempted. Whatever collects container logs should alert on this.
    echo "[backup] FAILED $(date -u +%FT%TZ)" >&2
  fi

  # Prune, or the volume fills silently and the first symptom is the
  # application being unable to write attachments.
  if [ -d "${BACKUP_DIR}" ]; then
    deleted=$(find "${BACKUP_DIR}" -type f -mtime "+${KEEP_DAYS}" -print -delete 2>/dev/null | wc -l)
    [ "${deleted}" -gt 0 ] && echo "[backup] pruned ${deleted} file(s) older than ${KEEP_DAYS} days"
  fi
done
