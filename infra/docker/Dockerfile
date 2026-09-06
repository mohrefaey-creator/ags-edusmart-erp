# AGS EduSmart ERP application image.
#
# Multi-stage: the builder carries the compilers and the Node toolchain needed to
# build Frappe's asset bundles; the runtime carries neither. That is worth about
# 1.4 GB per image and, more importantly, removes a compiler from a container
# that faces the internet.
#
# ---------------------------------------------------------------------------
# Two base-image constraints that are NOT free choices. Both were found by a
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
RUN bench get-app --branch ${ERPNEXT_BRANCH}   --resolve-deps erpnext \
 && bench get-app --branch ${HRMS_BRANCH}      --resolve-deps hrms \
 && bench get-app --branch ${EDUCATION_BRANCH} --resolve-deps education

# The AGS layer is copied from this repository rather than fetched, so the image
# is reproducible from the commit that built it.
COPY --chown=frappe:frappe apps/ags_edusmart /home/frappe/frappe-bench/apps/ags_edusmart
RUN ./env/bin/pip install --no-cache-dir -e apps/ags_edusmart \
 && echo "ags_edusmart" >> sites/apps.txt

RUN bench build --production \
 && find . -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && rm -rf /home/frappe/.cache /home/frappe/frappe-bench/apps/*/node_modules

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

COPY --chown=frappe:frappe infra/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER frappe
WORKDIR /home/frappe/frappe-bench
ENV PATH="/home/frappe/.local/bin:/home/frappe/frappe-bench/env/bin:${PATH}"

EXPOSE 8000 9000

# The health check hits Frappe itself, not just the port: a gunicorn master with
# every worker wedged still accepts connections.
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/method/ping || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
