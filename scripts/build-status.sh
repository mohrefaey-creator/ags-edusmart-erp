#!/usr/bin/env bash
# What is the image build actually doing right now?
#
# `tail` on the log is misleading during long steps — a build compiling
# translations or bundling assets can go minutes without writing a line, which
# looks identical to a stall. This reports the step, whether the process is
# alive, and whether it is burning CPU.
set -uo pipefail

LOG=${LOG:-/tmp/ags-image-build.log}

printf 'step        : %s\n' "$(grep -oE '^Step [0-9]+/[0-9]+' "${LOG}" 2>/dev/null | tail -1)"
printf 'last line   : %s\n' "$(tail -1 "${LOG}" 2>/dev/null | tr -d '\r' | cut -c1-90)"
printf 'log age     : %s s since last write\n' \
  "$(( $(date +%s) - $(stat -c %Y "${LOG}" 2>/dev/null || date +%s) ))"

alive=$(pgrep -fc 'docker build' 2>/dev/null || echo 0)
printf 'build procs : %s\n' "${alive}"

# The build runs inside a container; its CPU is what tells you it is working.
printf 'busiest     :\n'
ps -eo pcpu=,rss=,comm= --sort=-pcpu 2>/dev/null | head -4 | while read -r cpu rss comm; do
  printf '                %5s%%  %5s MB  %s\n' "${cpu}" "$((rss / 1024))" "${comm}"
done

printf 'wsl memory  : %s\n' "$(free -m | sed -n 2p | tr -s ' ')"
