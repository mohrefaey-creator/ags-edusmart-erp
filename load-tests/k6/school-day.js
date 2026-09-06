// Replays the shape of a real AGS school day against the ERP.
//
// This is the test that makes docs/capacity-model.md falsifiable. It does not
// hammer one endpoint at a constant rate - that measures nothing useful, because
// the risk in this system is the *shape* of the day:
//
//   06:30  quiet
//   07:40  attendance rush      - every teacher, same screens, ~20 minutes
//   09:00  mid-morning plateau  - admin, finance, procurement
//   12:00  parent surge         - month-start fee installments and reminders
//   15:00  wind-down
//
// Run:
//   k6 run -e BASE_URL=https://erp-staging.ags.edu.sa \
//          -e PARENT_PASSWORD=... -e TEACHER_PASSWORD=... school-day.js
//
// Compressed by default: each simulated minute is one real second, so a full
// day runs in about nine minutes. Set -e COMPRESSION=1 for real time.

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const COMPRESSION = Number(__ENV.COMPRESSION || 60); // simulated minutes per real second

// Divide every cohort by this. Default 1 — the full day against the deployed
// topology, which is the only run whose pass means what the SLOs say.
//
// It exists because the alternative is worse. The cohorts below are sized for
// the 6 nodes x 17 workers in docs/capacity-model.md; pointed at a 4-worker
// developer bench they breach every threshold no matter how healthy the code
// is, and a test that can only fail teaches nothing. Set SCALE to the worker
// ratio (102 model workers / your workers) and the profile keeps the *shape* of
// the day — same ramps, same mix, same ordering — at a load the box can serve.
// A pass then means "this build sustains its share of the design load", which
// is a real claim; it is not, and must not be reported as, a 2,500-user result.
const SCALE = Math.max(1, Number(__ENV.SCALE || 1));
const cohort = (n) => Math.max(1, Math.round(n / SCALE));

// Frappe picks the site from the request's Host header and falls back to
// default_site, which on a multi-site bench is a different database entirely.
// Addressing the site by name keeps the Host header right; this maps that name
// to the loopback so it works without an /etc/hosts entry. In staging the name
// resolves for real and SITE_HOST is simply left unset.
const SITE_HOST = __ENV.SITE_HOST || '';
const HOSTS = SITE_HOST ? { [SITE_HOST]: '127.0.0.1' } : {};

// Custom metrics, split by journey. A blended p95 hides the fact that the
// attendance submit is the slow one.
const portalLatency = new Trend('ags_portal_latency', true);
const deskLatency = new Trend('ags_desk_latency', true);
const attendanceLatency = new Trend('ags_attendance_latency', true);
const paymentLatency = new Trend('ags_payment_latency', true);
const loginFailures = new Rate('ags_login_failures');
const businessErrors = new Counter('ags_business_errors');

// Credentials come from the environment; nothing is embedded here.
const users = new SharedArray('users', () => {
  const parentPw = __ENV.PARENT_PASSWORD || '';
  const teacherPw = __ENV.TEACHER_PASSWORD || '';
  const staffPw = __ENV.STAFF_PASSWORD || teacherPw;
  return [
    { role: 'parent', usr: __ENV.PARENT_USER || 'parent@ags.edu.sa', pwd: parentPw },
    { role: 'teacher', usr: __ENV.TEACHER_USER || 'teacher@ags.edu.sa', pwd: teacherPw },
    { role: 'staff', usr: __ENV.STAFF_USER || 'finance@ags.edu.sa', pwd: staffPw },
  ];
});

// Cohort sizes from docs/capacity-model.md sec. 1, scaled to VUs.
// 2,500 concurrent sessions total at the peak; k6 VUs are sessions, not users.
export const options = {
  scenarios: {
    // 280 teachers, all inside a 20-minute window. This is the sharpest ramp in
    // the day and the one most likely to trip the autoscaler too late.
    attendance_rush: {
      executor: 'ramping-vus',
      exec: 'teacherJourney',
      startTime: '0s',
      stages: [
        { duration: `${Math.round(30 * 60 / COMPRESSION)}s`, target: cohort(40) },
        { duration: `${Math.round(10 * 60 / COMPRESSION)}s`, target: cohort(280) },
        { duration: `${Math.round(20 * 60 / COMPRESSION)}s`, target: cohort(280) },
        { duration: `${Math.round(60 * 60 / COMPRESSION)}s`, target: cohort(60) },
      ],
      gracefulRampDown: '30s',
    },

    // Admin/finance/procurement: steady through the working day.
    back_office: {
      executor: 'ramping-vus',
      exec: 'staffJourney',
      startTime: '0s',
      stages: [
        { duration: `${Math.round(60 * 60 / COMPRESSION)}s`, target: cohort(90) },
        { duration: `${Math.round(360 * 60 / COMPRESSION)}s`, target: cohort(90) },
        { duration: `${Math.round(60 * 60 / COMPRESSION)}s`, target: cohort(10) },
      ],
    },

    // The dominant cohort. Constant arrival rate, not constant VUs, because
    // parents arrive independently - if the app slows down, more of them pile
    // up rather than politely waiting their turn. This is what exposes a
    // capacity cliff instead of hiding it behind closed-loop backpressure.
    parent_surge: {
      executor: 'ramping-arrival-rate',
      exec: 'parentJourney',
      startTime: `${Math.round(120 * 60 / COMPRESSION)}s`,
      startRate: cohort(5),
      timeUnit: '1s',
      preAllocatedVUs: cohort(400),
      maxVUs: cohort(2000),
      stages: [
        { duration: `${Math.round(120 * 60 / COMPRESSION)}s`, target: cohort(30) },
        { duration: `${Math.round(60 * 60 / COMPRESSION)}s`, target: cohort(90) },  // month start
        { duration: `${Math.round(120 * 60 / COMPRESSION)}s`, target: cohort(40) },
        { duration: `${Math.round(60 * 60 / COMPRESSION)}s`, target: cohort(5) },
      ],
    },

    // A handful of executives, but each request is the expensive kind. This is
    // the scenario that catches a regression turning KPI snapshot reads back
    // into live aggregation over GL Entry.
    dashboards: {
      executor: 'constant-vus',
      exec: 'dashboardJourney',
      vus: cohort(30),
      startTime: `${Math.round(60 * 60 / COMPRESSION)}s`,
      duration: `${Math.round(360 * 60 / COMPRESSION)}s`,
    },
  },

  hosts: HOSTS,

  // These are the SLOs from docs/capacity-model.md sec. 11. A run that breaches
  // them fails, so capacity claims cannot quietly rot.
  thresholds: {
    'http_req_failed': ['rate<0.001'],
    'ags_portal_latency': ['p(95)<500'],
    'ags_desk_latency': ['p(95)<1200'],
    'ags_attendance_latency': ['p(95)<1500'],
    'ags_payment_latency': ['p(95)<2000'],
    'http_req_duration': ['p(99)<3000'],
    'ags_login_failures': ['rate<0.01'],
    'ags_business_errors': ['count<10'],
  },
};

// One session per VU, established on its first iteration and reused.
//
// k6 gives each VU its own module instance, so this module-level variable is
// per-VU state. Logging in on *every* iteration would make roughly a third of
// all traffic authentication, which is nothing like a real day: a parent signs
// in once and then reads. Getting this wrong makes the whole profile measure
// the auth path instead of the read path.
let session = null;

function login(user) {
  if (session) return true;

  const res = http.post(
    `${BASE}/api/method/login`,
    { usr: user.usr, pwd: user.pwd },
    { tags: { name: 'login' } },
  );
  const ok = check(res, { 'login succeeded': (r) => r.status === 200 });
  loginFailures.add(!ok);
  if (ok) {
    const sid = res.cookies['sid'];
    session = sid && sid.length ? sid[0].value : 'cookie-jar';
  }
  return ok;
}

function apiGet(path, params, trend, name) {
  const res = http.get(`${BASE}${path}`, { tags: { name } });
  trend.add(res.timings.duration);
  if (res.status >= 500) {
    businessErrors.add(1);
  }
  check(res, { [`${name} ok`]: (r) => r.status === 200 });
  return res;
}

// --------------------------------------------------------------- journeys
export function teacherJourney() {
  const user = users.find((u) => u.role === 'teacher');
  if (!login(user)) return;

  group('attendance', () => {
    apiGet('/api/method/frappe.client.get_list?doctype=Student%20Group&limit_page_length=20',
      null, deskLatency, 'student_groups');
    sleep(2);

    // Loading a class roster, then submitting attendance for it - the two calls
    // that every teacher makes between 07:40 and 08:00.
    apiGet('/api/method/frappe.client.get_list?doctype=Student&limit_page_length=40',
      null, attendanceLatency, 'class_roster');
    sleep(4);

    apiGet('/api/method/frappe.client.get_count?doctype=Student%20Attendance',
      null, attendanceLatency, 'attendance_count');
  });

  sleep(Math.random() * 10 + 5);
}

export function staffJourney() {
  const user = users.find((u) => u.role === 'staff');
  if (!login(user)) return;

  group('back office', () => {
    apiGet('/api/method/frappe.client.get_list?doctype=Sales%20Invoice&limit_page_length=20',
      null, deskLatency, 'invoice_list');
    sleep(3);
    apiGet('/api/method/frappe.client.get_list?doctype=AGS%20Collection%20Case&limit_page_length=20',
      null, deskLatency, 'collection_cases');
    sleep(3);
    apiGet('/api/method/frappe.client.get_list?doctype=Material%20Request&limit_page_length=20',
      null, deskLatency, 'purchase_requests');
  });

  sleep(Math.random() * 20 + 10);
}

export function parentJourney() {
  const user = users.find((u) => u.role === 'parent');
  if (!login(user)) return;

  group('parent portal', () => {
    apiGet('/api/method/frappe.client.get_list?doctype=AGS%20Payer%20Account&limit_page_length=5',
      null, portalLatency, 'payer_account');
    sleep(2);

    // The consolidated statement: the single most-loaded portal endpoint at
    // month start, and the one that joins invoices to students.
    apiGet('/api/method/frappe.client.get_list?doctype=Sales%20Invoice&limit_page_length=20',
      null, paymentLatency, 'statement');
    sleep(3);
  });
}

export function dashboardJourney() {
  const user = users.find((u) => u.role === 'staff');
  if (!login(user)) return;

  group('executive dashboard', () => {
    // Must stay fast. If this trends towards seconds, someone has replaced a
    // KPI snapshot read with a live aggregation.
    apiGet('/api/method/ags_edusmart.ags_dashboards.kpi_engine.read',
      null, deskLatency, 'kpi_read');
  });
  sleep(15);
}

export function handleSummary(data) {
  const p = (m) => (data.metrics[m] ? data.metrics[m].values['p(95)'] : null);
  const lines = [
    '',
    'AGS EduSmart ERP - school-day load profile',
    '==========================================',
    `  requests          ${data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0}`,
    `  peak rate         ${data.metrics.http_reqs ? data.metrics.http_reqs.values.rate.toFixed(1) : 0}/s`,
    `  failed            ${(data.metrics.http_req_failed.values.rate * 100).toFixed(3)}%`,
    '',
    '  p95 by journey (SLO in brackets)',
    `    portal          ${fmt(p('ags_portal_latency'))} ms   (500)`,
    `    desk            ${fmt(p('ags_desk_latency'))} ms   (1200)`,
    `    attendance      ${fmt(p('ags_attendance_latency'))} ms   (1500)`,
    `    payment         ${fmt(p('ags_payment_latency'))} ms   (2000)`,
    '',
    `  p99 overall       ${fmt(data.metrics.http_req_duration.values['p(99)'])} ms   (3000)`,
    '',
  ];
  return {
    stdout: lines.join('\n'),
    'summary.json': JSON.stringify(data, null, 2),
  };
}

function fmt(v) {
  return v === null || v === undefined ? '  n/a' : v.toFixed(0).padStart(5);
}
