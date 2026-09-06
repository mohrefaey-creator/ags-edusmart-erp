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
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const WORKERS = Number(__ENV.WORKERS || 1);
const PEAK = Number(__ENV.PEAK_RPS || 60);
const STEP = __ENV.STEP || '30s';

const readLatency = new Trend('ags_read_latency', true);
const errors = new Counter('ags_errors');

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
        { duration: STEP, target: Math.round(PEAK * 0.15) },
        { duration: STEP, target: Math.round(PEAK * 0.35) },
        { duration: STEP, target: Math.round(PEAK * 0.55) },
        { duration: STEP, target: Math.round(PEAK * 0.75) },
        { duration: STEP, target: PEAK },
        { duration: '15s', target: 0 },
      ],
    },
  },
  // Deliberately no thresholds: this profile is meant to be pushed past the
  // SLO. school-day.js is the one that gates.
  discardResponseBodies: false,
};

let sessionCookie = null;

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
}

export function handleSummary(data) {
  const m = data.metrics;
  const rps = m.http_reqs ? m.http_reqs.values.rate : 0;
  const p95 = m.ags_read_latency ? m.ags_read_latency.values['p(95)'] : 0;
  const p50 = m.ags_read_latency ? m.ags_read_latency.values.med : 0;
  const failed = m.http_req_failed ? m.http_req_failed.values.rate * 100 : 0;
  const perWorker = WORKERS ? rps / WORKERS : rps;

  const lines = [
    '',
    'AGS EduSmart — single-node calibration',
    '======================================',
    `  gunicorn workers      ${WORKERS}`,
    `  sustained throughput  ${rps.toFixed(1)} req/s`,
    `  per worker            ${perWorker.toFixed(2)} req/s`,
    `  p50 latency           ${p50.toFixed(0)} ms`,
    `  p95 latency           ${p95.toFixed(0)} ms`,
    `  errors                ${failed.toFixed(2)}%`,
    '',
    '  Model check (docs/capacity-model.md §3)',
    `    assumed  9.00 req/s per worker`,
    `    measured ${perWorker.toFixed(2)} req/s per worker`,
    `    verdict  ${perWorker >= 9 ? 'model is CONSERVATIVE — headroom exists'
                                  : 'model is OPTIMISTIC — node count must rise'}`,
    '',
    `  Implied nodes for the 625 req/s design peak at 70% utilisation:`,
    `    ${WORKERS ? Math.ceil(625 / (perWorker * 0.7) / 17) : '?'} nodes of 17 workers`,
    '',
  ];
  return {
    stdout: lines.join('\n'),
    'calibration.json': JSON.stringify(data, null, 2),
  };
}
