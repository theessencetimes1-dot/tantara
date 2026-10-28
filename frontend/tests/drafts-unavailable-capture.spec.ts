import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test';

const apiOrigin = (process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010').replace(/\/$/, '');
const shots = '../docs/screenshots';

async function authenticate(page: Page, api: APIRequestContext) {
  const response = await api.post(`${apiOrigin}/api/v1/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.status()).toBe(200);
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
  return token;
}
async function capture(page: Page, path: string) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path, fullPage: true });
}

test('capture honest model-unavailable state with editable review skeleton', async ({ page }) => {
  test.setTimeout(120_000);
  const api = await request.newContext();
  const token = await authenticate(page, api);
  const headers = { Authorization: `Bearer ${token}` };
  const originalSettings = await api
    .get(`${apiOrigin}/api/v1/settings/ai`, { headers })
    .then((response) => response.json());
  const settingsResult = await api.patch(`${apiOrigin}/api/v1/settings/ai`, {
    headers,
    data: { base_url: 'http://127.0.0.1:9/v1', model: originalSettings.model },
  });
  expect(settingsResult.status()).toBe(200);
  try {
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto('/drafts');
    const caseSelect = page.locator('#case');
    await expect(caseSelect).toBeVisible();
    await caseSelect.selectOption({ label: 'ABC Pvt. Ltd. vs. XYZ Ltd.' });
    await page.getByText(/Choose from \d+ case documents/).click();
    const sourceRow = page.locator('.draft-source').first();
    await expect(sourceRow).toBeVisible();
    await sourceRow.click();
    await expect(sourceRow.locator('input')).toBeChecked();
    await page.getByRole('button', { name: 'Generate Draft' }).click();
    await expect(page.getByRole('status')).toContainText('local model is unavailable', { timeout: 30_000 });
    await expect(page.locator('.draft-editor')).toContainText('[REVIEW:');
    await expect(page.locator('.draft-editor')).toBeEditable();
    await expect(page.getByRole('button', { name: 'Retry generation' })).toBeVisible();
    await expect(page.locator('[aria-busy="true"], .skeleton, [class*="skeleton"]')).toHaveCount(0);
    await capture(page, `${shots}/draft-model-unavailable-desktop-1440-real.png`);
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, `${shots}/draft-model-unavailable-mobile-390-real.png`);
  } finally {
    await api.patch(`${apiOrigin}/api/v1/settings/ai`, {
      headers,
      data: { base_url: originalSettings.base_url, model: originalSettings.model },
    });
    await api.dispose();
  }
});
