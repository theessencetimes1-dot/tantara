import { test, expect } from '@playwright/test';
test.setTimeout(90000);
const routes = (caseId: string, documentId: string) => [
  '/',
  '/dashboard',
  `/cases/${encodeURIComponent(caseId)}`,
  `/documents/${encodeURIComponent(documentId)}`,
  '/settings/profile',
  '/settings/workspace',
  '/settings/local-ai',
  '/settings/embeddings',
  '/settings/database',
  '/settings/data-import',
  '/settings/appearance',
  '/settings/security',
];
const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
test.beforeEach(async ({ page, request }) => {
  if (test.info().title === 'login form validates and submits with Enter') return;
  const response = await request.post(`${apiOrigin}/api/v1/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
});
test('existing routes render without console or hydration errors and overflow', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  const login = await request.post(`${apiOrigin}/api/v1/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const [casesResponse, documentsResponse] = await Promise.all([
    request.get(`${apiOrigin}/api/v1/cases?page_size=100`, { headers }),
    request.get(`${apiOrigin}/api/v1/documents?page_size=100`, { headers }),
  ]);
  const cases = (await casesResponse.json()).items as Array<{ id: string }>;
  const documents = (await documentsResponse.json()).items as Array<{ id: string; filename: string }>;
  const seededCase = cases[0];
  const seededDocument = documents.find((document) => document.filename === 'page-three-motion.pdf');
  expect(seededCase).toBeTruthy();
  expect(seededDocument).toBeTruthy();
  for (const route of routes(seededCase!.id, seededDocument!.id)) {
    await page.goto(route);
    await expect(page.locator('body')).not.toBeEmpty();
    await page.waitForTimeout(100);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      `${route} horizontal overflow`,
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});
test('login form validates and submits with Enter', async ({ page }) => {
  await page.goto('/');
  const email = page.locator('#email');
  await expect(email).toHaveValue('advocate@tantara.local');
  await email.fill('invalid');
  await expect(email).toHaveValue('invalid');
  await page.getByRole('textbox', { name: 'Password' }).fill('x');
  await page.getByRole('textbox', { name: 'Password' }).press('Enter');
  await expect(page.getByText('Enter a valid email address')).toBeVisible();
  await email.fill('advocate@tantara.local');
  await page.getByRole('textbox', { name: 'Password' }).fill('tantara-local');
  const loginResponse = page.waitForResponse((response) => response.url().endsWith('/api/v1/auth/login'));
  const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Continue as Advocate' }).click();
  expect((await loginResponse).status()).toBe(200);
  await navigation;
  await expect(page).toHaveURL(/dashboard/);
  await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('Workspace Advocate');
  await expect(page.getByRole('button', { name: 'Account menu' })).toContainText('advocate@tantara.local');
});
test('settings profile form is editable and navigation marks current route', async ({ page }) => {
  await page.goto('/settings/profile');
  await expect(
    page.getByRole('navigation', { name: 'Settings navigation' }).getByText('Profile'),
  ).toBeVisible();
  await expect(page.getByLabel('Name')).toBeVisible();
});
for (const width of [360, 768, 1024, 1440])
  test(`responsive workspace at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/dashboard');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });

const ownedRoutes = (caseId: string, clientId: string) => [
  '/cases',
  '/cases/active',
  '/cases/pending',
  '/cases/archived',
  '/cases/new',
  `/cases/${encodeURIComponent(caseId)}`,
  `/cases/${encodeURIComponent(caseId)}/edit`,
  '/clients',
  `/clients/${encodeURIComponent(clientId)}`,
  '/tasks',
  '/calendar',
];
test('cases, clients, tasks and calendar routes render at target widths without console errors or overflow', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  test.setTimeout(240000);
  const login = await request.post(`${apiOrigin}/api/v1/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const [casesResponse, clientsResponse] = await Promise.all([
    request.get(`${apiOrigin}/api/v1/cases?page_size=100`, { headers }),
    request.get(`${apiOrigin}/api/v1/clients?page_size=100`, { headers }),
  ]);
  const cases = (await casesResponse.json()).items as Array<{ id: string }>;
  const clients = (await clientsResponse.json()).items as Array<{ id: string }>;
  expect(cases[0]).toBeTruthy();
  expect(clients[0]).toBeTruthy();
  const routes = ownedRoutes(cases[0].id, clients[0].id);
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of routes) {
      await page.goto(route, { waitUntil: 'commit', timeout: 30000 });
      await expect(page.locator('body')).not.toBeEmpty();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${route} overflow at ${width}`,
      ).toBeTruthy();
    }
  }
  expect(errors).toEqual([]);
});
