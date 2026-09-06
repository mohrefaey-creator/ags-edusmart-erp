// Measure what one node actually delivers, so the capacity model stops being
// arithmetic and starts being extrapolation from a measurement.
//
// docs/capacity-model.md §3 rests on one assumption:
//
//     a gunicorn worker serves ~9 req/s at a ~110 ms blended service time
//
// Every node count downstream comes from that number. This profile finds the
// knee on a single node by ramping arrival rate until p95 crosses the SLO, then
// reports the throughput per worker so the model can be corrected.
//
//   k6 run -e BASE_URL=http://localhost:8010 \
//          -e WORKERS=4 \
//          -e USER=Administrator -e PASSWORD=... \
//          calibrate.js
//
// Arrival rate, not VUs, on purpose: a closed-loop VU model throttles itself
// when the server slows, which hides the knee instead of finding it.

import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const WORKERS = Number(__ENV.WORKERS || 1);
const PEAK = Number(__ENV.PEAK_RPS || 60);
const STEP_S = Number(__ENV.STEP_SECONDS || 30);
const HOLD_S = Number(__ENV.HOLD_SECONDS || 60);

// The portal read SLO from school-day.js. Throughput measured while p95 is
// above this is not capacity, it is queueing.
const READ_SLO_MS = 500;

const readLatency = new Trend('ags_read_latency', true);
// Measured over the flat hold only — see the note on the stages below.
const peakLatency = new Trend('ags_peak_latency', true);
const peakReqs = new Counter('ags_peak_reqs');
const errors = new Counter('ags_errors');

// The window, in seconds from test start, during which arrival rate is flat at
// PEAK. Everything before it is ramp.
const HOLD_FROM = STEP_S * 4;
const HOLD_TO = HOLD_FROM + HOLD_S;

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 2,
      timeUnit: '1s',
      // Enough VUs that k6 itself is never the bottleneck: at 500 ms p95 and
      // PEAK req/s you need ~PEAK/2 in flight, so this is generous headroom.
      preAllocatedVUs: Math.max(50, PEAK * 2),
      maxVUs: Math.max(200, PEAK * 8),
      stages: [
        { duration: `${STEP_S}s`, target: Math.round(PEAK * 0.25) },
        { duration: `${STEP_S}s`, target: Math.round(PEAK * 0.5) },
        { duration: `${STEP_S}s`, target: Math.round(PEAK * 0.75) },
        { duration: `${STEP_S}s`, target: PEAK },
        // The stage that matters. Every stage above *interpolates* toward its
        // target, so the arrival rate is still climbing throughout them —
        // averaging over the whole run would report roughly half the rate the
        // server actually sustained and would libel the capacity model as
        // optimistic. Only this flat hold is a throughput measurement.
        { duration: `${HOLD_S}s`, target: PEAK },
        { duration: '15s', target: 0 },
      ],
    },
  },
  // Deliberately no thresholds: this profile is meant to be pushed past the
  // SLO. school-day.js is the one that gates.
  discardResponseBodies: false,
};

export function setup() {
  const usr = __ENV.USER || 'Administrator';
  const pwd = __ENV.PASSWORD || '';
  const res = http.post(`${BASE}/api/method/login`, { usr, pwd });
  if (res.status !== 200) {
    throw new Error(`login failed (${res.status}) — pass -e USER and -e PASSWORD`);
  }
  const cookies = res.cookies['sid'];
  return { sid: cookies && cookies.length ? cookies[0].value : null };
}

// A representative read mix. Weighted towards the endpoints that actually
// dominate the 07:00-15:00 window (docs/capacity-model.md §2): portal list
// reads, a desk list, and a KPI dashboard read.
const ENDPOINTS = [
  { w: 5, path: '/api/method/frappe.client.get_list?doctype=Sales%20Invoice&limit_page_length=20' },
  { w: 3, path: '/api/method/frappe.client.get_list?doctype=Student&limit_page_length=20' },
  { w: 2, path: '/api/method/frappe.client.get_list?doctype=AGS%20Fee%20Plan&limit_page_length=20' },
  { w: 2, path: '/api/method/ags_edusmart.ags_dashboards.kpi_engine.read' },
  { w: 1, path: '/api/method/frappe.client.get_count?doctype=Student' },
];

const WEIGHTED = ENDPOINTS.flatMap((e) => Array(e.w).fill(e.path));

export default function (data) {
  const path = WEIGHTED[Math.floor(Math.random() * WEIGHTED.length)];
  const params = { headers: {} };
  if (data && data.sid) params.headers['Cookie'] = `sid=${data.sid}`;

  const res = http.get(`${BASE}${path}`, params);
  readLatency.add(res.timings.duration);
  if (res.status >= 400) errors.add(1);
  check(res, { 'ok': (r) => r.status === 200 });

  // Attribute this request to the flat hold if that is where it landed.
  const elapsed = exec.instance.currentTestRunDuration / 1000;
  if (elapsed >= HOLD_FROM && elapsed < HOLD_TO) {
    peakReqs.add(1);
    peakLatency.add(res.timings.duration);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const val = (name, key) => (m[name] ? m[name].values[key] : 0);

  // Throughput and latency from the flat hold only.
  const holdReqs = val('ags_peak_reqs', 'count');
  const rps = holdReqs / HOLD_S;
  const p95 = val('ags_peak_latency', 'p(95)');
  const p50 = val('ags_peak_latency', 'med');
  const failed = val('http_req_failed', 'rate') * 100;
  const perWorker = WORKERS ? rps / WORKERS : rps;

  // Throughput achieved while p95 is over the SLO is requests piling up in the
  // listen queue, not capacity. Saying so is the difference between a
  // calibration and a number that flatters the model.
  const withinSlo = p95 > 0 && p95 < READ_SLO_MS;

  const lines = [
    '',
    'AGS EduSmart — single-node calibration',
    '======================================',
    `  gunicorn workers      ${WORKERS}`,
    `  measured over         the flat ${HOLD_S}s hold at ${PEAK} req/s offered`,
    `                        (ramp stages excluded — they are not throughput)`,
    '',
    `  sustained throughput  ${rps.toFixed(1)} req/s`,
    `  per worker            ${perWorker.toFixed(2)} req/s`,
    `  p50 latency           ${p50.toFixed(0)} ms`,
    `  p95 latency           ${p95.toFixed(0)} ms  (SLO ${READ_SLO_MS} ms)`,
    `  errors                ${failed.toFixed(2)}%`,
    '',
  ];

  if (!withinSlo) {
    lines.push(
      '  ** p95 is ABOVE the read SLO at this offered rate. **',
      '  The node was saturated, so the throughput above is the queue draining,',
      `  not sustainable capacity. Re-run with a lower -e PEAK_RPS (try`,
      `  ${Math.max(2, Math.round(PEAK * 0.6))}) until p95 lands under ${READ_SLO_MS} ms, and calibrate from that run.`,
      '',
    );
  } else {
    lines.push(
      '  Model check (docs/capacity-model.md §3)',
      '    assumed  9.00 req/s per worker',
      `    measured ${perWorker.toFixed(2)} req/s per worker`,
      `    verdict  ${perWorker >= 9 ? 'model is CONSERVATIVE — headroom exists'
                                     : 'model is OPTIMISTIC — node count must rise'}`,
      '',
      '  Implied nodes for the 625 req/s design peak at 70% utilisation:',
      `    ${perWorker > 0 ? Math.ceil(625 / (perWorker * 0.7 * 17)) : '?'} nodes of 17 workers`,
      '',
      `  NOTE: the offered rate was capped at ${PEAK} req/s and p95 stayed under`,
      '  the SLO, so this is a lower bound on the node\'s capacity, not its knee.',
      `  Raise -e PEAK_RPS until p95 crosses ${READ_SLO_MS} ms to find the actual knee.`,
      '',
    );
  }

  return {
    stdout: lines.join('\n'),
    'calibration.json': JSON.stringify(data, null, 2),
  };
}
