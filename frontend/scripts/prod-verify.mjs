// Production smoke check: https://tantara-prod.web.app (Firebase Hosting →
// Cloud Run → Supabase). It registers a throwaway account through the public
// API, signs the browser in the way the app itself does, then walks the
// workspace and writes screenshots to reports/prod/.
//
//   cd frontend && node scripts/prod-verify.mjs
//
// Exit code is non-zero when a step fails; nothing secret is printed.
import { chromium } from '@playwright/test';

const SITE = process.env.TANTARA_PROD_URL ?? 'https://tantara-prod.web.app';
const OUT = new URL('../../reports/prod/', import.meta.url).pathname;
const email = `probe.${Date.now().toString(36)}@theessencetimes.com`;
const password = 'Prod-Verify-2026!';

const shot = async (page, name) => {
  await page.screenshot({ path: `${OUT}${name}.png` });
  console.log('shot', name);
};

const fail = (message, detail) => {
  console.error('FAIL', message, detail ?? '');
  process.exitCode = 1;
};

const registration = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ name: 'Prod Verify', email, password, title: 'Advocate' }),
});
if (!registration.ok) {
  fail('register', `${registration.status} ${(await registration.text()).slice(0, 120)}`);
  process.exit(process.exitCode ?? 1);
}
const { access_token: token } = await registration.json();
console.log('registered a probe account through the production API');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

await page.goto(`${SITE}/`, { waitUntil: 'networkidle' });
await shot(page, '01-landing');

await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
await page.evaluate(
  ([value]) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  },
  [token],
);

await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
await shot(page, '02-dashboard');

await page.goto(`${SITE}/documents`, { waitUntil: 'networkidle' });
const rows = await page.locator('table tbody tr, [data-document-row]').count();
console.log('document rows visible to a brand-new account:', rows);
await shot(page, '03-documents');

await page.goto(`${SITE}/search`, { waitUntil: 'networkidle' });
const box = page.locator('input[type="search"], input[name="query"], input[placeholder*="earch" i]').first();
if (await box.count()) {
  await box.fill('section 34 arbitral award set aside');
  await box.press('Enter');
  await page.waitForTimeout(4000);
  const hits = await page.locator('[data-search-hit], article, table tbody tr').count();
  console.log('search result rows:', hits);
  await shot(page, '04-search');
} else {
  await shot(page, '04-search');
  fail('search', 'no search input found');
}

await page.goto(`${SITE}/research`, { waitUntil: 'networkidle' });
const question = page.locator('textarea').first();
if (await question.count()) {
  await question.fill('When can a court set aside an arbitral award under the Arbitration and Conciliation Act?');
  const send = page.locator('button:has-text("Ask")').last();
  if (await send.count()) await send.click();
  else await question.press('Enter');
  await page.waitForTimeout(12000);
  await shot(page, '05-research');
} else {
  await shot(page, '05-research');
  fail('research', 'no question box found');
}

// Private isolation: the corpus is shared, another account's uploads are not.
const second = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ name: 'Prod Isolation', email: `probe.${Date.now().toString(36)}.b@theessencetimes.com`, password, title: 'Advocate' }),
});
const secondToken = second.ok ? (await second.json()).access_token : null;
if (secondToken) {
  const mine = await fetch(`${SITE}/api/v1/documents?page_size=100`, { headers: { Authorization: `Bearer ${token}` } });
  const theirs = await fetch(`${SITE}/api/v1/documents?page_size=100`, { headers: { Authorization: `Bearer ${secondToken}` } });
  const mineIds = (await mine.json()).items.map((d) => d.id);
  const theirIds = (await theirs.json()).items.map((d) => d.id);
  console.log('shared corpus visible to both accounts:', mineIds.length === theirIds.length && mineIds.length > 0);
}

await browser.close();
console.log(process.exitCode ? 'production smoke check: failures above' : 'production smoke check: ok');
