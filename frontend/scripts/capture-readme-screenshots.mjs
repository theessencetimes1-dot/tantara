import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const webOrigin = process.env.TANTARA_WEB_URL ?? 'http://127.0.0.1:3010';
const output = path.resolve(process.cwd(), '../docs/screenshots');
const modules = [
  ['Dashboard', '/dashboard', 'dashboard'],
  ['Cases', '/cases', 'cases'],
  ['Clients', '/clients', 'clients'],
  ['Tasks', '/tasks', 'tasks'],
  ['Calendar', '/calendar', 'calendar'],
  ['Documents', '/documents', 'documents'],
  ['Search', '/search', 'search'],
  ['Research', '/research', 'research'],
  ['Drafts', '/drafts', 'drafts'],
  ['Autofill', '/autofill', 'autofill'],
  ['Bundles', '/bundles', 'bundles'],
  ['Strategy', '/strategy', 'strategy'],
  ['Community', '/community', 'community'],
  ['Settings', '/settings/profile', 'settings-profile'],
];
const forbidden =
  /E2E Matter|Strategy source test|Minimal case|All-day event check|UTC calendar all-day proof|1793[0-9]{6}/;
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });
  const page = await context.newPage();
  const login = await page.request.post(`${apiOrigin}/api/v1/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL ?? 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD ?? 'tantara-local',
    },
  });
  if (!login.ok()) throw new Error(`Login failed: ${login.status()} ${await login.text()}`);
  const token = (await login.json()).access_token;
  const censusResponse = await page.request.get(`${apiOrigin}/api/v1/cases?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!censusResponse.ok()) throw new Error(`Case census failed: ${censusResponse.status()}`);
  const census = await censusResponse.json();
  if (census.total !== 12) throw new Error(`Expected 12 seeded advocate cases, got ${census.total}`);
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);

  const stamp = new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  const captured = [];
  for (const [label, route, slug] of modules) {
    if (!slug?.trim()) throw new Error(`Refusing to create a screenshot for ${route} with an empty slug`);
    for (const viewport of [
      { width: 1440, height: 900, suffix: '1440x900' },
      { width: 390, height: 844, suffix: '390x844' },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const response = await page.goto(new URL(route, webOrigin).toString(), {
        waitUntil: 'domcontentloaded',
      });
      if (!response || response.status() >= 400) throw new Error(`${route} returned ${response?.status()}`);
      await page.locator('.sidebar .nav a[href]').first().waitFor({ state: 'attached' });
      await page.locator('main h1').first().waitFor({ state: 'visible' });
      if (route === '/dashboard') {
        await page.waitForFunction(
          (expected) => {
            const cases = document.querySelector('.matter-tabs')?.textContent ?? '';
            const metrics = [...document.querySelectorAll('.dashboard-primary .metric-grid .metric')].map(
              (el) => el.textContent ?? '',
            );
            const text = document.body.innerText;
            return (
              cases.includes(`All Cases (${expected})`) &&
              metrics.length === 4 &&
              metrics.every((item) => /\d/.test(item)) &&
              !/Loading (research|activity|calendar)/i.test(text)
            );
          },
          census.total,
          { timeout: 30_000 },
        );
      }
      await page
        .waitForFunction(() => !/Loading…|Loading\.\.\./.test(document.body.innerText), { timeout: 30_000 })
        .catch(() => {
          throw new Error(`${route} did not finish loading before capture`);
        });
      const bodyText = await page.locator('body').innerText();
      if (forbidden.test(bodyText))
        throw new Error(`Refusing contaminated ${route} capture: ${bodyText.match(forbidden)?.[0]}`);
      const navCount = await page.locator('.sidebar .nav a[href]').count();
      if (navCount !== 14) throw new Error(`${route} has ${navCount} rail anchors, expected 14`);
      if (viewport.width === 390) {
        const width = await page.evaluate(() => document.documentElement.scrollWidth);
        if (width > 390) throw new Error(`${route} overflows mobile viewport (${width}px)`);
      }
      const name = `${slug}-${viewport.suffix}.png`;
      await page.screenshot({ path: path.join(output, name), fullPage: false });
      captured.push({ label, viewport: viewport.suffix, name });
      console.log(`captured ${route} ${viewport.suffix}: ${name}`);
    }
  }
  const readmePath = path.resolve(process.cwd(), '../README.md');
  let readme = await (await import('node:fs/promises')).readFile(readmePath, 'utf8');
  readme = readme.replace(
    /(\| [^|]+ \| !\[[^\]]+\]\(docs\/screenshots\/[^)]+\) \| !\[[^\]]+\]\(docs\/screenshots\/[^)]+\) \| [^|]+ \| )[^|]+ \| [^|]+( \|)/g,
    `$1${stamp} | ${stamp}$2`,
  );
  await writeFile(readmePath, readme);
  console.log(
    `captured ${captured.length} images from ${webOrigin}; case total ${census.total}; manifest timestamp ${stamp}`,
  );
} finally {
  await browser.close();
}
