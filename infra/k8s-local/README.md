# Local cluster

A disposable single-node [kind](https://kind.sigs.k8s.io) cluster that runs the
manifests in `../k8s/` so they can be exercised rather than asserted.

```bash
sudo bash scripts/install-k8s-tools.sh     # kubectl + kind, both pinned
sudo bash scripts/build-image.sh           # if ags/edusmart-erp:local is missing
sudo bash scripts/k8s-local-registry.sh    # registry + push
sudo bash scripts/k8s-local-up.sh          # create, deploy, wait, report
sudo bash scripts/k8s-verify.sh            # prove it actually works
kind delete cluster --name ags-erp         # when finished
```

The production manifests in `../k8s/` are never edited for local use. Everything
that differs is a patch in `kustomization.yaml`, so `git diff` on the base
always shows a production change and never a debugging convenience someone
forgot to revert.

## What a green run proves

- The manifests are valid, mutually consistent, and schedule.
- The image boots in-cluster in every role: web, three worker queues,
  scheduler, socketio.
- The startup, readiness and liveness probes pass against a real Frappe boot.
- The site-init → migrate → rollout ordering works, and the Jobs are idempotent.
- The Service routes and the app answers over it.
- Secrets and ConfigMap wiring reaches the process (the entrypoint's `wait_for`
  resolves the service names from the ConfigMap).

That is worth having. Four things were wrong the first time this was run, and
none of them were visible to `kubectl apply --dry-run`.

## What it does not prove

Do not quote a green run here as evidence about production.

| | Local | Production |
|---|---|---|
| Nodes | 1 | 6–10 web + workers, multi-zone |
| Web replicas | 1 | 6, autoscaling to 10 |
| Gunicorn workers | 2 | 17 |
| Web pod resources | 200m / 512Mi | 4 CPU / 8Gi |
| `sites` volume | ReadWriteOnce, local-path | **ReadWriteMany**, NFS/EFS/CephFS |
| MariaDB | one container, `emptyDir` | 16 vCPU / 64 GB primary + 2 replicas |
| Redis | two containers | three instances, tuned per role |

Four specific blind spots are worth naming, because each is a place where the
local run is silently reassuring:

**ReadWriteMany is untested.** The base PVC demands RWX because web pods and
workers both write attachments and generated PDFs. The overlay downgrades it to
RWO, which works only because every workload here is one replica on one node.
A RWO volume in production would appear to work with one replica and then fail
to schedule the second — the exact failure the base comment warns about.

**NetworkPolicies *are* enforced here** — which is the opposite of what this
document originally claimed. Older kindnet ignored NetworkPolicy; the version
shipped with kind 0.30 / Kubernetes 1.34 implements it, and the deploy proved
it the hard way: `default-deny-ingress` blocked the site-init Job from reaching
Redis, and the failure presented as a connection timeout against a Service
whose endpoints were perfectly healthy.

So a green run here does exercise the policies. Two things it taught:

- `allow-data-from-app` selects datastores by `tier in (database, redis)`. Those
  workloads live outside this repository, so that label is a contract with
  whatever provides MariaDB and Redis. An unlabelled datastore is not merely
  unprotected — the default-deny applies and nothing can reach it at all.
- `tier: site-init` had to be added to the allowed client list. It was missing
  because the Job itself was missing.

**The HPAs cannot act.** There is no metrics-server, so both
HorizontalPodAutoscalers report unknown metrics and never scale. They are
validated as objects, not as behaviour.

**The Ingress has no controller unless you install one.** `k8s-local-up.sh`
does not install ingress-nginx by default — on a 4 GB VM the memory is better
spent on the pods under test. The Ingress object applies and is inert; reach the
app with `kubectl -n ags-erp port-forward svc/ags-web 8000:8000`.

## Memory

The binding constraint is RAM, not CPU or disk. The first attempt at this used
`kind load docker-image`, which saves the 4.35 GB image to a tar and imports it
in one go; inside a 4 GB WSL VM that did not fail gracefully, it took the VM
down. Hence the registry: it streams compressed layers to disk, of which there
is plenty.

If pods sit in `Pending`, check `kubectl -n ags-erp describe pod ...` for
`Insufficient memory` before assuming anything is wrong with the manifests.
