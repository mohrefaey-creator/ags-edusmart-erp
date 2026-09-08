#!/usr/bin/env bash
# Run the database-free tests in a bare container.
#
#   sudo bash scripts/run-unit-tests.sh
#
# The suite splits along frappe's own test base classes: UnitTestCase needs no
# site, IntegrationTestCase does. This runs the first group, which means it needs
# neither Kubernetes nor MariaDB nor a site — just the image. On a machine where
# the cluster falls over every few minutes that is the difference between having
# a signal and having none, and in CI it is the fast gate that runs on every
# push before anything expensive starts.
#
# scripts/run-app-tests.sh runs the integration half against a real site.
set -uo pipefail

TAG=${TAG:-ags/edusmart-erp:local}
MODULES=${MODULES:-"ags_edusmart.tests.test_pure_logic ags_edusmart.tests.test_translations"}

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found — run scripts/build-image.sh" >&2; exit 1; }

docker run --rm --entrypoint /bin/bash "${TAG}" -c "
cd /home/frappe/frappe-bench/sites
python - <<'PY'
import sys, unittest
import frappe

# No site, no database: init with an empty site so frappe's module machinery is
# usable, then load the modules directly rather than going through bench, which
# would insist on a site that exists.
frappe.init(site='')

names = '''${MODULES}'''.split()
loader = unittest.TestLoader()
suite = unittest.TestSuite()
failed_to_load = []
for n in names:
    try:
        suite.addTests(loader.loadTestsFromName(n))
    except Exception as e:
        failed_to_load.append((n, e))

for n, e in failed_to_load:
    print('COULD NOT LOAD %s: %s: %s' % (n, type(e).__name__, e))

result = unittest.TextTestRunner(verbosity=2).run(suite)
print()
print('ran=%d failures=%d errors=%d skipped=%d unloadable=%d'
      % (result.testsRun, len(result.failures), len(result.errors),
         len(result.skipped), len(failed_to_load)))
sys.exit(0 if (result.wasSuccessful() and not failed_to_load) else 1)
PY
"
