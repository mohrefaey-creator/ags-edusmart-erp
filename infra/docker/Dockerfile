# AGS EduSmart ERP application image.
#
# Multi-stage: the builder carries the compilers and the Node toolchain needed to
# build Frappe's asset bundles; the runtime carries neither. That is worth about
# 1.4 GB per image and, more importantly, removes a compiler from a container
# that faces the internet.
#
# ---------------------------------------------------------------------------
# Three base-image constraints that are NOT free choices. Each was found by a
# build failing, not by reading docs:
#
#   Python 3.14 exactly.  frappe 16 pins `requires-python = ">=3.14,<3.15"`.
#     A 3.12 base fails minutes into `bench init` with a uv resolver message
#     ("the current Python version does not satisfy Python>=3.14,<3.15") that
#     never names the base image as the cause.
#
#   Node 24 or newer.  frappe's package.json declares `engines: {node: ">=24"}`.
#     Older Node builds assets with warnings and then fails at runtime in
#     socketio, which is far more expensive to diagnose than a build error.
#
#   Debian bookworm, not trixie.  wkhtmltopdf renders every fee invoice and
#     payslip, and it is not packaged in newer Debian releases.
#
#   cron.  `bench init` shells out to crontab; slim images have no cron, and
#     its absence aborts init with a message that never mentions it.
# ---------------------------------------------------------------------------

ARG PYTHON_IMAGE=python:3.14-slim-bookworm
ARG NODE_MAJOR=24

# ---------------------------------------------------------------------- builder
FROM ${PYTHON_IMAGE} AS builder

ARG NODE_MAJOR
ARG FRAPPE_BRANCH=version-16
ARG ERPNEXT_BRANCH=version-16
ARG HRMS_BRANCH=version-16
ARG EDUCATION_BRANCH=version-16

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl ca-certificates \
        libmariadb-dev pkg-config \
        libssl-dev libffi-dev \
        libxml2-dev libxslt1-dev zlib1g-dev \
        # `bench init` shells out to crontab to install the bench's schedule.
        # It is absent from slim images, and its absence aborts the whole init
        # with "There was a problem while creating /home/frappe/frappe-bench" —
        # a message that never mentions cron. Nothing in the running container
        # uses it: the scheduler is its own process (see entrypoint.sh).
        cron \
    && rm -rf /var/lib/apt/lists/*

# Node is needed only to build assets; it does not ship in the runtime stage.
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && yarn --version

RUN useradd -ms /bin/bash frappe
USER frappe
WORKDIR /home/frappe

RUN pip install --no-cache-dir --user frappe-bench
ENV PATH="/home/frappe/.local/bin:${PATH}"

# Pinned branches, not floating tags: an ERP that reprices fees differently
# after an unattended rebuild is worse than one that is a month behind.
RUN bench init \
        --frappe-branch ${FRAPPE_BRANCH} \
        --skip-redis-config-generation \
        --verbose \
        /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# Declared here rather than with the other branch args so that adding it does
# not invalidate the cached `bench init` layer above it.
ARG PAYMENTS_BRANCH=version-16

# Explicit URLs, and deliberately NO --resolve-deps.
#
# With --resolve-deps, fetching hrms re-resolves its dependency on the erpnext
# that was just installed, fails to match its version (the shallow clone has no
# symbolic upstream/HEAD, so the branch check errors), decides "Incompatible
# version of erpnext is already installed", and then tries to fetch an app
# literally named `frappe/erpnext` — producing
# `No such file or directory: './apps/frappe/erpnext/erpnext/__init__.py'`.
#
# Listing every app explicitly is what apps.json already does, so this also
# keeps the image and the deployment definition saying the same thing.
RUN bench get-app --branch ${ERPNEXT_BRANCH}   https://github.com/frappe/erpnext \
 && bench get-app --branch ${PAYMENTS_BRANCH}  https://github.com/frappe/payments \
 && bench get-app --branch ${HRMS_BRANCH}      https://github.com/frappe/hrms \
 && bench get-app --branch ${EDUCATION_BRANCH} https://github.com/frappe/education

# The AGS layer is copied from this repository rather than fetched, so the image
# is reproducible from the commit that built it.
COPY --chown=frappe:frappe apps/ags_edusmart /home/frappe/frappe-bench/apps/ags_edusmart
RUN ./env/bin/pip install --no-cache-dir -e apps/ags_edusmart \
 # `bench get-app` writes sites/apps.txt WITHOUT a trailing newline, so a bare
 # `echo >>` splices onto the last entry: `payments` + `ags_edusmart` becomes
 # the single line `paymentsags_edusmart`, and the next command dies with
 # `ModuleNotFoundError: No module named 'paymentsags_edusmart'` — which names
 # a module nobody wrote and points at nothing. The leading \n guarantees the
 # break; the sed removes the blank line it creates if one was already there.
 && printf '\nags_edusmart\n' >> sites/apps.txt \
 && sed -i '/^[[:space:]]*$/d' sites/apps.txt \
 # Printed so the layer's log carries proof the file is one app per line.
 && cat sites/apps.txt

# Every app's node_modules is build-only EXCEPT frappe's.
#
# apps/frappe/socketio.js requires its dependencies at *runtime* — it is a Node
# process, not a bundle — so deleting apps/frappe/node_modules to save space
# makes the socketio role die at startup with MODULE_NOT_FOUND and a require
# stack pointing at frappe/realtime/index.js. The other apps' node_modules are
# genuinely build-only. The `test -d` makes a future cleanup that removes
# frappe's fail the build rather than the cluster.
RUN bench build --production \
 && find . -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && rm -rf /home/frappe/.cache \
 && find apps -mindepth 2 -maxdepth 2 -name node_modules -type d \
      -not -path 'apps/frappe/*' -prune -exec rm -rf {} + \
 && test -d apps/frappe/node_modules

# ---------------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime

ARG NODE_MAJOR

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        # mariadb-client: bench needs it for backup/restore
        mariadb-client \
        libmariadb3 \
        # git is not optional here, despite nothing in the runtime cloning
        # anything. `bench` imports GitPython at module level, and GitPython
        # raises ImportError("Bad git executable") on import when the binary is
        # absent — so every role that shells out to bench (all three worker
        # queues, the scheduler, the migrate Job, and the `bench` escape hatch
        # the runbooks use for backup and restore) dies before running a line of
        # its own code. Only the web role, which execs gunicorn directly,
        # survives without it.
        git \
        # wkhtmltopdf renders every fee invoice and payslip
        wkhtmltopdf xfonts-75dpi xfonts-base \
        # Arabic shaping in generated PDFs; without these, invoices print boxes
        fonts-noto fonts-noto-core \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node 24 in the runtime too — socketio runs here, and Debian's packaged nodejs
# is far older than frappe's `engines: {node: ">=24"}`.
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version

RUN useradd -ms /bin/bash frappe
COPY --from=builder --chown=frappe:frappe /home/frappe /home/frappe

# Frappe's logging opens files under a logs/ directory on first use and does
# not create it. Without this the web role dies during startup on
# `FileNotFoundError: '/home/frappe/logs/cssutils.log'` — a log file, for a CSS
# library, taking the application down. Both locations are created because
# which one is used depends on how the bench path resolves for the process.
RUN mkdir -p /home/frappe/logs /home/frappe/frappe-bench/logs \
 && chown -R frappe:frappe /home/frappe/logs /home/frappe/frappe-bench/logs

COPY --chown=frappe:frappe infra/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER frappe
WORKDIR /home/frappe/frappe-bench
ENV PATH="/home/frappe/.local/bin:/home/frappe/frappe-bench/env/bin:${PATH}"

EXPOSE 8000 9000

# No HEALTHCHECK here, deliberately.
#
# One image serves six roles, and only the thing that starts the container knows
# which. A single healthcheck baked into the image was wrong twice over:
#
#   * it hit http://localhost:8000, which only the web role serves. The three
#     worker queues, the scheduler and socketio have nothing listening there, so
#     every one of them reported permanently unhealthy — and under any
#     restart-on-unhealthy policy would restart forever while working fine.
#   * it sent no Host header, so even the web role got a 404. Frappe picks the
#     site from Host, and a request naming a site it does not have is correctly
#     refused.
#
# Health is now defined where the role is: deploy/compose/compose.yaml gives web
# a healthcheck carrying the Host header, and infra/k8s/10-web.yaml gives it
# startup, readiness and liveness probes carrying the same.

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
