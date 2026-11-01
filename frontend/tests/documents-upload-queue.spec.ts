import { expect, test, type APIRequestContext } from '@playwright/test';

const api = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;

test('upload queue follows ingestion status through Ready and offers Open', async ({ page, request }) => {
  test.setTimeout(90000);
  const login = await request.post(`${api}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/documents');
  const name = `queue-ready-${Date.now()}.txt`;
  await page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: 'text/plain',
    buffer: Buffer.from('Short arbitration document for upload queue readiness.'),
  });
  const queueItem = page.locator('.documents-queue .queue-item').filter({ hasText: name });
  await expect(queueItem).toContainText('Ready', { timeout: 60000 });
  await expect(queueItem.getByRole('link', { name: 'Open' })).toBeVisible();
  const href = await queueItem.getByRole('link', { name: 'Open' }).getAttribute('href');
  expect(href).toMatch(/^\/documents\/[^/]+$/);
});
