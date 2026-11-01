import { chromium } from '@playwright/test';

const SITE = process.env.SITE ?? 'https://tantara-prod.web.app';
const stamp = Date.now();
const res = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    name: 'UI Check',
    email: `qa.uicheck.${stamp}@theessencetimes.com`,
    password: 'Tantra-Test-2026!',
    title: 'Advocate',
  }),
});
const token = (await res.json()).access_token;
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
await page.evaluate(
  ([value]) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  },
  [token],
);
await page.goto(`${SITE}/cases/new`, { waitUntil: 'networkidle' });
await page.waitForTimeout(4000);
const buttons = await page.locator('button').allInnerTexts();
console.log('buttons:', JSON.stringify(buttons.filter((b) => b.trim()).slice(0, 25)));
const selects = await page
  .locator('select')
  .evaluateAll((els) =>
    els.map((e) => ({
      label: e.getAttribute('aria-label') || e.name || e.id,
      options: Array.from(e.options).map((o) => o.text),
    })),
  );
console.log('selects:', JSON.stringify(selects));
const chunks = await page.evaluate(() =>
  Array.from(document.scripts)
    .map((s) => s.src)
    .filter((s) => s.includes('_next'))
    .slice(-4),
);
console.log('chunks:', JSON.stringify(chunks));
const clientArea = await page
  .locator('div, section')
  .filter({ has: page.locator('select') })
  .first()
  .innerHTML()
  .catch(() => 'n/a');
console.log('client area html:', String(clientArea).replace(/\s+/g, ' ').slice(0, 700));
console.log('has Add client text:', await page.locator('text=/add client/i').count());
console.log('page errors:', JSON.stringify((await page.evaluate(() => window.__errors ?? [])).slice(0, 3)));
await page.screenshot({ path: '/tmp/ui-check-cases-new.png', fullPage: false });
await browser.close();
