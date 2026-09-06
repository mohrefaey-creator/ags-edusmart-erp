#!/usr/bin/env bash
# Free what can be freed before a memory-hungry step.
#
# This box has 6.9 GB total with WSL bounded to 4 GB, and a Frappe asset build
# plus a load test do not both fit. Rather than guess, this reports the top
# consumers and stops the things that are safe to stop.
#
#   sudo bash scripts/free-memory.sh          # report only
#   sudo bash scripts/free-memory.sh --stop   # also stop the dev server
set -uo pipefail

echo "before:"
free -m | sed -n '1,2p' | sed 's/^/  /'

echo
echo "top consumers:"
ps -eo rss=,comm= --sort=-rss | head -8 | while read -r rss comm; do
  printf '  %6s MB  %s\n' "$((rss / 1024))" "${comm}"
done

if [ "${1:-}" = "--stop" ]; then
  echo
  # The dev server is disposable; MariaDB and Redis are not — stopping those
  # would take the site down and lose the queue.
  if pkill -f 'bench.*serve' 2>/dev/null; then
    echo "  stopped bench serve"
  fi
  if pkill -f 'gunicorn.*frappe.app' 2>/dev/null; then
    echo "  stopped a stray gunicorn"
  fi

  # Reclaim page cache. Harmless: it is cache, and the kernel refills it.
  sync
  echo 3 > /proc/sys/vm/drop_caches 2>/dev/null && echo "  dropped page cache"

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker container prune -f >/dev/null 2>&1 && echo "  pruned stopped containers"
  fi

  sleep 2
  echo
  echo "after:"
  free -m | sed -n '2p' | sed 's/^/  /'
fi
