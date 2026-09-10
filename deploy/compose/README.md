# Single-VM deployment

Runs the whole ERP on one machine with Docker Compose: the same image, the same
roles and the same entrypoint as `infra/k8s`, without the cluster.

Verified end to end by `scripts/compose-verify.sh`, which brings the stack up
against a throwaway site and checks that every role runs, that the app answers
over TLS through Caddy, that a request for the wrong host is refused, and that a
backup produces a real database dump.

## What the VM needs

| | |
|---|---|
| CPU | 4 vCPU minimum |
| RAM | 8 GB minimum, 16 GB comfortable |
| Disk | 60 GB, SSD |
| OS | anything with Docker Engine 24+ and the compose plugin |
| Network | ports 80 and 443 open to the internet |
| DNS | an A record for `SITE_NAME` pointing at the VM, **before first start** |

The DNS record has to exist first. Caddy asks Let's Encrypt for a certificate on
startup, and the HTTP-01 challenge is Let's Encrypt connecting back to that name
on port 80. No record, no certificate — and the production ACME endpoint
rate-limits failures, so getting this wrong repeatedly means waiting.

## First run

```bash
git clone <this repo> && cd "School ERP/deploy/compose"
cp .env.example .env
```

Edit `.env`. At minimum set `SITE_NAME`, `ACME_EMAIL`, and generate the two
passwords with `openssl rand -base64 30` — do not invent them.

Then build or pull the image, create the site, and start:

```bash
sudo bash ../../scripts/build-image.sh     # or set AGS_IMAGE to a pulled tag
docker compose --profile setup run --rm site-init
docker compose --profile setup run --rm migrate
docker compose up -d
```

`site-init` takes 15–30 minutes: it creates the site and installs six apps.
It is idempotent, so a re-run after a failure picks up where it left off.

Confirm:

```bash
docker compose ps
curl -sS https://$SITE_NAME/api/method/ping     # {"message":"pong"}
```

Log in as `Administrator` with the `ADMIN_PASSWORD` from `.env`.

## Upgrading

```bash
docker compose pull                              # or rebuild the image
docker compose --profile setup run --rm migrate  # schema first, always
docker compose up -d
```

Migrate before the app restarts, never alongside it. Two containers running
migrations against one site at the same time corrupts the schema, which is why
migrate is a one-shot with its own profile rather than a startup step.

There is a brief outage during `up -d`. One machine cannot do a rolling deploy;
that is the trade this shape makes.

## Backups

The `backup` service runs nightly at `BACKUP_AT_UTC` (default 22:15 UTC =
01:15 Riyadh) and keeps `BACKUP_KEEP_DAYS` of history, pruning older files so
the volume cannot fill silently.

Backups land **inside the `sites` volume**, on the same disk as the database.
That protects against a bad migration or a deleted record. It does not protect
against losing the VM. Copy them off the machine:

```bash
docker compose exec -T web tar -C /home/frappe/frappe-bench/sites/$SITE_NAME/private -c backups \
  | ssh backup-host 'cat > ags-$(date +%F).tar'
```

Run one by hand, and check it worked:

```bash
docker compose exec backup /usr/local/bin/entrypoint.sh backup --with-files
docker compose exec web ls -lh /home/frappe/frappe-bench/sites/$SITE_NAME/private/backups
```

**Test a restore before you need one.** An untested backup is a belief, not a
backup.

```bash
docker compose exec web bench --site $SITE_NAME restore \
  /home/frappe/frappe-bench/sites/$SITE_NAME/private/backups/<file>-database.sql.gz \
  --db-root-password "$DB_ROOT_PASSWORD"
```

## Operating

```bash
docker compose ps                       # what is running
docker compose logs -f web              # follow a service
sudo bash ../../scripts/compose-logs.sh # why something is restarting
docker compose restart web
```

`sudo bash ../../scripts/compose-verify.sh` re-runs the full check suite. It
rewrites `.env` with test values, so use it on a test host, not in production.

## What this gives up

No horizontal scaling, no rolling deploys, and the database shares a machine
with the application — a heavy report competes with the web tier for CPU.

The capacity model in `docs/capacity-model.md` sizes for 2,500 concurrent users
across six nodes. This is not that, and does not pretend to be. For one school
below roughly 500 concurrent users it is the right shape, and when it stops
being, `infra/k8s` is where to go — the image, the roles and the entrypoint move
across unchanged.

## Things that will bite

**`SITE_NAME` must match DNS and the site on disk.** Frappe picks which site to
serve from the request's `Host` header. If they disagree you get 404 on every
page from a perfectly healthy application. Caddy passes `Host` through
unmodified, which is why the app works at all.

**Never scale the scheduler.** Two schedulers double every scheduled job. For
the reminder ladder that means two messages to every parent.

**Do not run `AGS_IMAGE=...:latest` in production.** An unattended `docker
compose pull` that silently moves the ERP to a new version is how fees get
repriced without anyone deciding to. Use an immutable release tag.

**`DB_ROOT_PASSWORD` is baked into the database volume on first run.** Changing
it later in `.env` does not change the database — it just stops the application
connecting.
