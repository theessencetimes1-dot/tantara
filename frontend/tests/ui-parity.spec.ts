import { expect, test } from '@playwright/test';

const moduleRoutes = [
  '/dashboard',
  '/cases',
  '/clients',
  '/tasks',
  '/calendar',
  '/documents',
  '/search',
  '/research',
  '/drafts',
  '/autofill',
  '/bundles',
  '/strategy',
  '/community',
  '/settings/profile',
];

async function authenticate(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext,
) {
  const origin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
  const response = await request.post(`${origin}/api/v1/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
}

test('workspace navigation exposes all module routes and each route resolves', async ({ page, request }) => {
  test.setTimeout(120_000);
  await authenticate(page, request);
  await page.goto('/dashboard');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const paths = await nav
    .locator('a')
    .evaluateAll((links) => links.map((link) => new URL((link as HTMLAnchorElement).href).pathname));
  for (const route of moduleRoutes) expect(paths).toContain(route);
  const appOrigin = new URL(page.url()).origin;
  for (const route of paths) {
    const response = await request.get(`${appOrigin}${route}`);
    expect(response?.status(), `${route} should resolve`).toBeLessThan(400);
  }
  for (const [route, label] of [
    ['/autofill', 'Smart Autofill'],
    ['/bundles', 'Bundles'],
    ['/strategy', 'Strategy'],
    ['/search', 'Search'],
  ]) {
    const link = nav.getByRole('link', { name: label, exact: true });
    await expect(link).toHaveAccessibleName(label);
    await expect(link).toHaveAttribute('href', route);
    await link.click();
    await page.waitForURL((url) => url.pathname === route, { waitUntil: 'commit', timeout: 15_000 });
    const activeNavLink = page.locator('a[aria-current="page"]');
    await expect(activeNavLink).toHaveCount(1);
    await expect(activeNavLink).toHaveAttribute('href', route);
    const dashboardLink = page.getByRole('link', { name: 'Dashboard', exact: true }).first();
    await dashboardLink.click();
    await page.waitForURL((url) => url.pathname === '/dashboard', {
      waitUntil: 'commit',
      timeout: 15_000,
    });
    await expect(activeNavLink).toHaveCount(1);
    await expect(activeNavLink).toHaveAttribute('href', '/dashboard');
  }
});

test('settings section navigation keeps one visible page-level current link', async ({ page, request }) => {
  await authenticate(page, request);
  await page.goto('/settings/profile');
  const pageCurrent = page.locator('a[aria-current="page"]');
  await expect(pageCurrent).toHaveCount(1);
  await expect(pageCurrent).toHaveAttribute('href', '/settings/profile');
  await expect(
    page.getByRole('navigation', { name: 'Settings navigation' }).getByRole('link', { name: 'Profile' }),
  ).toHaveAttribute('aria-current', 'location');
});

test('shared shell matches measured desktop target geometry and artwork', async ({ page, request }) => {
  await authenticate(page, request);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard');
  const sidebar = page.locator('.sidebar');
  const header = page.locator('.topbar');
  await expect(sidebar).toBeVisible();
  await expect(page.locator('h1').first()).toBeVisible();
  const measurements = await page.evaluate(() => {
    const rail = document.querySelector('.sidebar')!;
    const topbar = document.querySelector('.topbar')!;
    const heading = document.querySelector('h1')!;
    const art = document.querySelector('.sidebar-art')!;
    return {
      railWidth: rail.getBoundingClientRect().width,
      railPosition: getComputedStyle(rail).position,
      railScrollWidth: rail.scrollWidth,
      railClientWidth: rail.clientWidth,
      pitch:
        document.querySelector('.nav a')!.getBoundingClientRect().height +
        Number.parseFloat(getComputedStyle(document.querySelector('.nav')!).rowGap),
      headerHeight: topbar.getBoundingClientRect().height,
      workspace: getComputedStyle(document.querySelector('.workspace')!).backgroundColor,
      headingFont: getComputedStyle(heading).fontFamily,
      artImage: getComputedStyle(art).backgroundImage,
    };
  });
  expect(measurements.railWidth).toBeGreaterThan(0);
  expect(measurements.railPosition).toBe('fixed');
  expect(measurements.railScrollWidth).toBeLessThanOrEqual(measurements.railClientWidth + 1);
  expect(measurements.pitch).toBeGreaterThan(36);
  expect(measurements.headerHeight).toBeGreaterThanOrEqual(60);
  expect(measurements.headerHeight).toBeLessThanOrEqual(80);
  expect(measurements.headingFont).toContain('Playfair');
  expect(measurements.artImage).toContain('legal-scales.jpg');
  await expect(page.locator('.brandmark')).not.toContainText('T');
  await expect(page.locator('.sidebar-art-rule')).toBeVisible();
  await expect(header).toBeVisible();
});

test('dashboard renders four metrics before Ask TANTARA and keeps both secondary totals compact', async ({
  page,
  request,
}) => {
  await authenticate(page, request);
  await page.goto('/dashboard');
  const cards = page.locator('.dashboard-primary .metric-grid .metric');
  await expect(cards).toHaveCount(4);
  await expect(cards.nth(0)).toContainText('Active Cases');
  await expect(cards.nth(1)).toContainText('Arbitrations Pending');
  await expect(cards.nth(2)).toContainText('Hearings This Week');
  await expect(cards.nth(3)).toContainText('Documents Added');
  const ask = page.locator('.ask-panel');
  await expect(ask).toBeVisible();
  for (const chip of [
    'Procedure under Arbitration Act',
    'Recent arbitral awards',
    'Draft statement of claim',
    'Relief options',
  ]) {
    await expect(ask.getByRole('button', { name: chip })).toBeVisible();
  }
  await expect(page.locator('.secondary-summary .secondary-summary-item')).toHaveCount(2);
});

test('strategy evidence follow-up arrives prefilled in Research Desk', async ({ page, request }) => {
  await authenticate(page, request);
  const question = 'Follow up on strategy evidence for the selected case';
  await page.goto(`/research?case_id=case-evidence&question=${encodeURIComponent(question)}`);
  await expect(page.getByRole('textbox', { name: 'Research question' })).toHaveValue(question);
});
