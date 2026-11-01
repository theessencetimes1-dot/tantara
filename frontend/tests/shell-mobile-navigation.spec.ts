import { expect, test } from '@playwright/test';

const expectedNavigation = [
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

test('hamburger navigation exposes all destinations and Calendar/Settings work at mobile and tablet widths', async ({
  page,
  request,
}) => {
  const api = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;
  const response = await request.post(`${api}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/dashboard');
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const nav = page.getByRole('navigation', { name: 'Main navigation' });
    await expect(nav).toBeVisible();
    expect(
      await nav
        .locator('a')
        .evaluateAll((links) => links.map((link) => new URL((link as HTMLAnchorElement).href).pathname)),
    ).toEqual(expectedNavigation);
    await nav.getByRole('link', { name: 'Calendar' }).click();
    await expect(page).toHaveURL(/\/calendar$/);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await nav.getByRole('link', { name: 'Settings' }).click();
    await expect(page).toHaveURL(/\/settings\/profile$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
});
