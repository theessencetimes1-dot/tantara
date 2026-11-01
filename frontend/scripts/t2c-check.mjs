// Focused re-check of test 2c: does the desk answer all five questions about the
// uploaded arbitration agreement when the research is scoped to that matter?
// Usage: node scripts/t2c-check.mjs --base https://tantara-prod.web.app
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';

const index = process.argv.indexOf('--base');
const SITE = index >= 0 ? process.argv[index + 1] : 'https://tantara-prod.web.app';
const OUT = process.env.OUT_DIR ?? 'reports/evidence/after-prod';
const SOURCE = process.env.UPLOAD_FILE ?? '../legal_docs/TANTRA-TEST-ARBITRATION.txt';
const Q =
  'What is the agreement reference number in the uploaded arbitration agreement, who are the two parties, ' +
  'what is the seat of arbitration, and how many arbitrators are provided for?';

const stamp = Date.now();
async function api(token, route, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  if (options.body !== undefined && !headers['content-type']) headers['content-type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${SITE}/api/v1${route}`, { ...options, headers });
  const text = await response.text();
  try {
    return { status: response.status, body: JSON.parse(text) };
  } catch {
    return { status: response.status, body: text.slice(0, 300) };
  }
}

const account = (
  await api(null, '/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      name: 'Desk Recheck',
      email: `qa.t2crecheck.${stamp}@theessencetimes.com`,
      password: 'Tantra-Test-2026!',
      title: 'Advocate',
    }),
  })
).body;

const created = await api(account.access_token, '/cases', {
  method: 'POST',
  body: JSON.stringify({
    title: 'Zenith Traders vs. Orion Components',
    claimant: 'Zenith Traders',
    respondent: 'Orion Components',
    forum: 'SIAC',
    seat: 'Mumbai',
    governing_law: 'Indian law',
    claim_amount: 12500000,
  }),
});
const caseId = created.body?.id;

const upload = await api(account.access_token, '/documents/upload', {
  method: 'POST',
  body: (() => {
    const boundary = '----tantraT2c';
    const bytes = fs.readFileSync(path.resolve(SOURCE));
    return Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${path.basename(SOURCE)}"\r\n` +
        'Content-Type: text/plain\r\n\r\n' + bytes.toString('utf8') + `\r\n--${boundary}--\r\n`,
    );
  })(),
  headers: { 'content-type': 'multipart/form-data; boundary=----tantraT2c' },
});
const docId = upload.body?.document_id ?? upload.body?.document?.id;
if (docId && caseId) await api(account.access_token, `/documents/${docId}`, { method: 'PATCH', body: JSON.stringify({ case_id: caseId }) });

let status = 'unknown';
for (let attempt = 0; attempt < 30; attempt += 1) {
  const listed = await api(account.access_token, `/documents/${docId}`);
  status = listed.body?.status ?? 'unknown';
  if (['ready', 'failed'].includes(status)) break;
  await new Promise((resolve) => setTimeout(resolve, 3000));
}
console.log(`case=${caseId} document=${docId} status=${status}`);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
await page.evaluate((value) => {
  localStorage.setItem('tantara_token', value);
  document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
}, account.access_token);
await page.goto(`${SITE}/research`, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: /new research/i }).first().click().catch(() => {});
await page.waitForTimeout(2500);
const caseScope = page.getByLabel('Case');
if (await caseScope.count()) await caseScope.selectOption({ index: 1 }).catch(() => {});
await page.waitForTimeout(1500);
await page.locator('textarea').first().fill(Q);
await page.getByRole('button', { name: /^ask|send/i }).last().click();

let body = '';
let previous = '';
for (let attempt = 0; attempt < 40; attempt += 1) {
  await page.waitForTimeout(3000);
  body = await page.locator('main').innerText();
  if (attempt > 2 && body === previous && body.length > 400) break;
  previous = body;
}
fs.mkdirSync(OUT, { recursive: true });
await page.screenshot({ path: path.join(OUT, '17-research-uploaded-agreement.png'), fullPage: true });
const answers = {
  reference: body.includes('TANTRA-TEST-2026-001'),
  partyA: /zenith/i.test(body),
  partyB: /orion/i.test(body),
  seat: /mumbai/i.test(body),
  soleArbitrator: /sole|one arbitrator|1 arbitrator/i.test(body),
};
console.log(JSON.stringify({ id: 'T2c', answers, chars: body.length }, null, 2));
await browser.close();
