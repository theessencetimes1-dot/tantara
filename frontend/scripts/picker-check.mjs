import { chromium } from '@playwright/test';
const SITE = 'https://tantara-prod.web.app';
const stamp = Date.now();
const res = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ name: 'Picker Check', email: `qa.pickercheck.${stamp}@theessencetimes.com`, password: 'Tantra-Test-2026!', title: 'Advocate' }),
});
const token = (await res.json()).access_token;
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.on('response', async (r) => {
  if (r.status() >= 400 || r.url().includes('/clients')) {
    let body = '';
    try { body = (await r.text()).slice(0, 160); } catch {}
    console.log(`resp ${r.status()} ${r.request().method()} ${r.url().replace(SITE, '')} ${body}`);
  }
});
await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
await page.evaluate(([v]) => { localStorage.setItem('tantara_token', v); document.cookie = `tantara_token=${v}; Path=/; SameSite=Lax`; }, [token]);
await page.goto(`${SITE}/cases/new`, { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);
const btn = page.getByRole('button', { name: '＋ Add client' });
console.log('fullwidth button count:', await btn.count());
const anyBtn = page.getByRole('button', { name: /add client/i });
console.log('any add-client button count:', await anyBtn.count(), JSON.stringify(await anyBtn.allInnerTexts()));
await anyBtn.first().click();
await page.waitForTimeout(1000);
const box = page.getByRole('textbox', { name: 'New client name' });
console.log('new client box count:', await box.count());
await box.first().fill('Zenith Traders Pvt Ltd');
await box.first().press('Enter');
await page.waitForTimeout(3000);
console.log('status text:', JSON.stringify((await page.locator('[role="status"]').allInnerTexts()).slice(0, 3)));
console.log('client select value:', JSON.stringify(await page.getByLabel('Client').inputValue().catch(() => 'ERR')));
console.log('selects:', JSON.stringify(await page.locator('select').evaluateAll((els) => els.map((e) => ({
  aria: e.getAttribute('aria-label'), name: e.name, id: e.id, value: e.value,
  options: Array.from(e.options).map((o) => ({ v: o.value.slice(0, 8), t: o.text })),
})))));
console.log('client inputs:', JSON.stringify(await page.locator('input').evaluateAll((els) => els.filter((e) => /client/i.test(e.getAttribute('aria-label') || e.name || e.id || '')).map((e) => ({ tag: e.tagName, aria: e.getAttribute('aria-label'), value: e.value })))));
await page.screenshot({ path: '/tmp/picker-after.png' });
await browser.close();
