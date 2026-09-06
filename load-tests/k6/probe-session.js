// Smallest thing that answers: does a k6 VU carry its session cookie from
// /api/method/login into the next request?
//
// The school-day profile was failing 93% of requests with "Login to access",
// i.e. arriving as Guest, while the same calls made with curl and a cookie jar
// returned 200. That difference is the whole bug, and this isolates it from the
// 8-minute profile around it.
//
//   k6 run -e BASE_URL=http://ags.localhost:8010 -e SITE_HOST=ags.localhost \
//          -e USER=lt.staff001@loadtest.invalid -e PASSWORD=... probe-session.js

import http from 'k6/http';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const SITE_HOST = __ENV.SITE_HOST || '';

export const options = {
  vus: 1,
  iterations: 1,
  hosts: SITE_HOST ? { [SITE_HOST]: '127.0.0.1' } : {},
};

export default function () {
  const login = http.post(`${BASE}/api/method/login`, {
    usr: __ENV.USER || 'Administrator',
    pwd: __ENV.PASSWORD || '',
  });
  console.log(`login status   = ${login.status}`);
  console.log(`login body     = ${(login.body || '').slice(0, 120)}`);
  console.log(`set-cookie sid = ${login.cookies['sid'] ? login.cookies['sid'][0].value.slice(0, 12) + '...' : 'NONE'}`);

  const jar = http.cookieJar();
  const forUrl = jar.cookiesForURL(`${BASE}/api/method/ping`);
  console.log(`jar keys       = ${Object.keys(forUrl).join(',') || 'EMPTY'}`);

  const res = http.get(
    `${BASE}/api/method/frappe.client.get_list?doctype=Sales%20Invoice&limit_page_length=5`,
  );
  console.log(`follow-up      = ${res.status}`);
  console.log(`follow-up body = ${(res.body || '').slice(0, 160).replace(/\s+/g, ' ')}`);

  const who = http.get(`${BASE}/api/method/frappe.auth.get_logged_user`);
  console.log(`logged user    = ${who.status} ${(who.body || '').slice(0, 80)}`);
}
