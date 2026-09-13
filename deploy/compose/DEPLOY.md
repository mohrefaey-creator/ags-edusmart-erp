# Deployment runbook — blank VM to first login

Every step ends with a check. Do not move on until it passes; every later
failure is harder to diagnose than the one in front of you.

Time: about 90 minutes, of which 30 is waiting for site creation.

---

## Before you start

You need all four of these. Missing any one stops the run at step 4 or 5.

- [ ] **A VM**: Ubuntu 24.04, 4 vCPU, **8 GB RAM minimum**, 60 GB SSD, public IP.
- [ ] **SSH access** to it as a user with sudo.
- [ ] **A domain**, with an **A record already pointing at the VM's IP**.
      Check: `nslookup erp.ags.edu.sa` on your own machine returns the VM's IP.
- [ ] **The repo on GitHub** with the `Release image` workflow having run green
      at least once. Check: the Actions tab shows a green run, and its summary
      names a `sha-…` tag.

The DNS record is the one people skip. Caddy asks Let's Encrypt for a
certificate the moment it starts, and Let's Encrypt proves you own the name by
connecting back to it on port 80. No record, no certificate. The production
endpoint also rate-limits failed attempts — five per hour per name — so
starting before DNS is ready can cost you an hour of waiting.

---

## 1. Connect

```bash
ssh <user>@<vm-ip>
```

Check: you have a shell, and `sudo true` asks for nothing or a password you
know.

---

## 2. Prepare the VM

```bash
git clone https://github.com/<owner>/<repo>.git ags-erp
cd ags-erp
sudo bash scripts/vm-bootstrap.sh
```

Installs Docker with the compose plugin, opens 22/80/443 in the firewall and
closes everything else, enables OS security updates, and adds you to the
`docker` group.

Log out and back in so the group applies.

Check:

```bash
docker compose version      # prints a version
sudo ufw status             # 22, 80, 443 ALLOW; default deny incoming
```

---

## 3. Configure

```bash
cd ags-erp/deploy/compose
cp .env.example .env
nano .env
```

Set these four. Leave the rest at their defaults for now.

| variable | set to |
|---|---|
| `SITE_NAME` | your domain, exactly as in DNS — `erp.ags.edu.sa` |
| `ACME_EMAIL` | a mailbox someone reads; Let's Encrypt sends expiry warnings here |
| `DB_ROOT_PASSWORD` | output of `openssl rand -base64 30` |
| `ADMIN_PASSWORD` | output of `openssl rand -base64 30` |
| `AGS_IMAGE` | the `sha-…` tag from the green Actions run, e.g. `ghcr.io/<owner>/ags-edusmart-erp:sha-abc123def456` |

`SITE_NAME` is not cosmetic. Frappe chooses which site to serve from the
request's `Host` header. If this does not match what browsers send, every page
is a 404 from a perfectly healthy application.

Record the two passwords somewhere safe now. `DB_ROOT_PASSWORD` is baked into
the database volume on first run; changing it in `.env` later does not change
the database, it just stops the application connecting.

Check:

```bash
docker compose config >/dev/null && echo OK
```

Prints `OK`. Anything else is a typo in `.env`.

---

## 4. Pull the image

If the GitHub repo is private, log in first with a token that has
`read:packages`:

```bash
echo <token> | docker login ghcr.io -u <github-username> --password-stdin
```

Then:

```bash
docker compose pull
```

Check:

```bash
docker images | grep ags-edusmart-erp
```

Shows the image, about 4.8 GB.

---

## 5. Start the datastores

```bash
docker compose up -d mariadb redis-cache redis-queue
```

Check — wait for `healthy`, up to a minute:

```bash
docker compose ps mariadb
```

---

## 6. Create the site

```bash
docker compose --profile setup run --rm site-init
```

This creates the site and installs six apps. **It takes 15–30 minutes** and
prints a lot. It is safe to re-run: if it fails partway, run it again and it
continues from where it stopped.

Check — the last lines are:

```
[site-init] done
frappe
erpnext
payments
hrms
education
ags_edusmart
```

---

## 7. Migrate

```bash
docker compose --profile setup run --rm migrate
```

Check — ends with `Queued rebuilding of search index` and no traceback.

---

## 8. Start everything

```bash
docker compose up -d
```

Caddy now requests the certificate. Watch it happen:

```bash
docker compose logs -f caddy
```

You are looking for `certificate obtained successfully`. Press Ctrl-C once you
see it. If instead you see `challenge failed` or `connection refused`, DNS is
not pointing at this VM yet, or port 80 is blocked upstream of the firewall
(a cloud security group, for instance). Fix that; Caddy retries on its own.

Check — all eight running, web healthy:

```bash
docker compose ps
```

```
backup          running
caddy           running
mariadb         running (healthy)
redis-cache     running
redis-queue     running
scheduler       running
socketio        running
web             running (healthy)
worker-default  running
worker-long     running
worker-short    running
```

Web takes about 90 seconds to go from `health: starting` to `healthy`.

---

## 9. Verify from outside

From **your own machine**, not the VM:

```bash
curl -sS https://erp.ags.edu.sa/api/method/ping
```

Check: `{"message":"pong"}` with **no certificate warning**. A warning here
means Caddy is still on a temporary certificate; wait a minute and retry.

Then open `https://erp.ags.edu.sa` in a browser. You get the Frappe login page
with a padlock.

---

## 10. First login and setup

Log in as `Administrator` with `ADMIN_PASSWORD`.

Frappe shows a setup wizard. Complete it — language, country (Saudi Arabia),
timezone (Asia/Riyadh), currency (SAR). Then:

1. **Create the Company** (Setup → Company). This is the operation that used
   to fail on a fresh site with `Could not find Warehouse Type: Transit`; the
   fix is in the image, and this is where you confirm it.
2. Set the fiscal year.
3. Create the first real user and give them the AGS roles.

Check: the Company saves without error and appears in the list.

---

## 11. Prove the backup works — today, not the day you need it

```bash
docker compose exec backup /usr/local/bin/entrypoint.sh backup --with-files
docker compose exec web ls -lh /home/frappe/frappe-bench/sites/erp.ags.edu.sa/private/backups
```

Check: a `…-database.sql.gz` from just now, more than a few KB.

Backups land on the VM's own disk. That protects against a bad migration; it
does not protect against losing the VM. Set up an off-machine copy this week —
README.md has the one-liner — and **test a restore once** before there is data
you would miss.

---

## Upgrading later

1. Push to `main` (or tag `v1.x.y`). Wait for the `Release image` run to go
   green and note its `sha-…` tag.
2. On the VM, set `AGS_IMAGE` in `.env` to that tag.
3. ```bash
   docker compose pull
   docker compose --profile setup run --rm migrate
   docker compose up -d
   ```

Migrate **before** `up -d`, always. Two containers migrating one site at the
same time corrupts the schema, which is why migrate is a one-shot with its own
profile and not a startup step. Expect about a minute of outage during `up -d`;
one machine cannot do a rolling deploy.

**Rollback**: set `AGS_IMAGE` back to the previous tag, `docker compose up -d`.
If the migration changed the schema, restore the pre-upgrade backup first. Take
one before every upgrade — step 11, thirty seconds.

---

## When something is wrong

```bash
docker compose ps                        # what is running and healthy
docker compose logs --tail=50 web        # the last thing it said
sudo bash ../../scripts/compose-logs.sh  # why anything is restarting
```

| symptom | almost always |
|---|---|
| every page is 404, web is healthy | `SITE_NAME` does not match the browser's Host |
| certificate warning that never clears | DNS not pointing here, or port 80 blocked upstream |
| workers restarting, "broken pipe" | Redis rejecting connections — check `infra/redis/*.conf` has `protected-mode no` |
| `Access denied for user` | `DB_ROOT_PASSWORD` changed after first run |
| disk full | backups not pruning, or Docker logs — `vm-bootstrap.sh` sets rotation |
