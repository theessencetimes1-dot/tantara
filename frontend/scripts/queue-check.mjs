// Queue render check: does the upload queue display a state, or crash on a missing status?
// Usage: node scripts/queue-check.mjs --base https://tantara-prod.web.app
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '@playwright/test';

const index = process.argv.indexOf('--base');
const SITE = index >= 0 ? process.argv[index + 1] : 'https://tantara-prod.web.app';
const OUT = process.env.OUT_DIR ?? 'reports/evidence/queue-check';
fs.mkdirSync(OUT, { recursive: true });

const stamp = Date.now();
const email = `qa.queuecheck.${stamp}@theessencetimes.com`;
const created = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ name: 'Queue Check', email, password: 'Tantra-Test-2026!', title: 'Advocate' }),
});
const token = (await created.json()).access_token;

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error.message).slice(0, 120)));
await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
await page.evaluate((value) => {
  localStorage.setItem('tantara_token', value);
  document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
}, token);

const file = path.join(process.env.TMPDIR ?? '/tmp', `queue-probe-${stamp}.txt`);
fs.writeFileSync(file, 'Queue probe agreement.\nReference: TANTRA-QUEUE-001. Seat: Mumbai.\n');
await page.goto(`${SITE}/documents`, { waitUntil: 'networkidle' });
await page.setInputFiles('input[type="file"]', file);
let label = '';
for (let attempt = 0; attempt < 20; attempt += 1) {
  await page.waitForTimeout(3000);
  label = (await page.locator('text=/Upload queue/i').first().innerText().catch(() => '')).replace(/\s+/g, ' ');
  console.log(`${attempt * 3}s queue="${label.slice(0, 120)}"`);
  if (/ready|complete|indexed|failed/i.test(label)) break;
}
await page.screenshot({ path: path.join(OUT, 'queue-check.png') });
await page.reload({ waitUntil: 'networkidle' });
const badge = await page.locator('main').innerText();
console.log('library mentions Ready:', /ready/i.test(badge));
console.log('page errors:', errors.length ? errors.join(' | ') : 'none');
await browser.close();
fs.unlinkSync(file);
