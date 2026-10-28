import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test';

const apiOrigin = (process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010').replace(/\/$/, '');
const shots = 'test-results';

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

test('demo draft is identified as a scaffold while generated unstructured text keeps the review alert', async ({
  page,
  request,
}) => {
  const token = await authenticate(page, request);
  const headers = { Authorization: `Bearer ${token}` };
  const list = await request.get(`${apiOrigin}/api/v1/drafts?page=1&page_size=100`, { headers });
  expect(list.status()).toBe(200);
  const demoDraft = (await list.json()).items.find((row: { is_demo?: boolean }) => row.is_demo);
  expect(demoDraft, 'demo seed includes a never-generated outline scaffold').toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/drafts?id=${demoDraft.id}`);
  await expect(
    page.getByRole('heading', { name: 'Template scaffold — nothing generated yet' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate draft' })).toBeVisible();
  await expect(page.locator('.draft-unrecognized')).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Generated text needs editing — structure not recognised' }),
  ).toHaveCount(0);
  await expect(page.getByText('No citations yet — generate or attach sources.')).toBeVisible();

  const created = await request.post(`${apiOrigin}/api/v1/drafts`, {
    headers,
    data: {
      title: 'Generated unstructured review',
      document_type: 'Pleading',
      content_markdown:
        '# Unstructured generated content\n\nPlain generated paragraph without a recognised section.',
    },
  });
  expect(created.status()).toBe(200);
  const draft = await created.json();
  const version = await request.post(`${apiOrigin}/api/v1/drafts/${draft.id}/versions`, {
    headers,
    data: {
      content_markdown: draft.content_markdown,
      change_note: 'Generated model outline',
    },
  });
  expect(version.status()).toBe(200);
  await page.goto(`/drafts?id=${draft.id}`);
  await expect(
    page.getByRole('heading', { name: 'Generated text needs editing — structure not recognised' }),
  ).toBeVisible();
  await expect(page.locator('.draft-unrecognized')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Template scaffold — nothing generated yet' })).toHaveCount(
    0,
  );
});
