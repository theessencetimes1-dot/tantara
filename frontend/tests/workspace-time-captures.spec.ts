import { expect, test } from '@playwright/test';

const api = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;

async function authenticate(page: import('@playwright/test').Page) {
  const response = await page.request.post(`${api}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
}

async function loginToken(page: import('@playwright/test').Page) {
  const response = await page.request.post(`${api}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function assertCaptureReady(page: import('@playwright/test').Page) {
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
  await expect(page.locator('body')).not.toBeEmpty();
  expect(await page.evaluate(() => localStorage.getItem('tantara_token'))).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
}

test('captures seeded Tasks at 1440 by 900 without test-created records', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await authenticate(page);
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
  await expect(page.locator('.task-groups')).toBeVisible();
  await assertCaptureReady(page);
  await expect(page.getByText('Workspace wall time check')).toHaveCount(0);
  await page.screenshot({ path: '../docs/screenshots/tasks-1440x900.png', fullPage: false });
});

test('captures seeded Calendar at 1440 by 900 without test-created records', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await authenticate(page);
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible();
  await expect(page.locator('[data-calendar-settled="true"]')).toBeVisible();
  await assertCaptureReady(page);
  await expect(page.getByText('UTC calendar all-day proof')).toHaveCount(0);
  await page.screenshot({ path: '../docs/screenshots/calendar-1440x900.png', fullPage: false });
});

test('dashboard case table headers remain separate at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await authenticate(page);
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Case Management' })).toBeVisible();
  const table = page.locator('.matter-wrap.compact .matter-table');
  await expect(table).toBeVisible();
  await expect(table.getByRole('columnheader', { name: /Tribunal \/ Institution/ })).toBeVisible();
  await expect(table.getByRole('columnheader', { name: /Next Hearing/ })).toBeVisible();
  const tribunal = await table.locator('thead th').nth(1).boundingBox();
  const hearing = await table.locator('thead th').nth(2).boundingBox();
  expect(tribunal).toBeTruthy();
  expect(hearing).toBeTruthy();
  expect(tribunal!.x + tribunal!.width).toBeLessThanOrEqual(hearing!.x);
  await assertCaptureReady(page);
  await page.screenshot({ path: '../docs/screenshots/dashboard-1440x900.png', fullPage: false });
});

test('captures the real seeded bundle list and 44-page bundle detail', async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await loginToken(page);
  const response = await page.request.get(`${api}/bundles?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  const { items } = (await response.json()) as {
    items: Array<{
      id: string;
      name: string;
      case_title: string;
      page_count: number;
      section_count: number;
      file_size_bytes: number | null;
      downloadable: boolean;
    }>;
  };
  const bundle = items.find((item) => item.page_count === 44 && item.downloadable);
  expect(bundle, 'fresh demo seed includes a downloadable 44-page bundle').toBeTruthy();
  expect(bundle!.case_title).toBeTruthy();
  expect(bundle!.section_count).toBeGreaterThan(0);
  expect(bundle!.file_size_bytes).toBeGreaterThan(0);
  const mappingResponse = await page.request.get(`${api}/bundles/${bundle!.id}/preview`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(mappingResponse.ok()).toBeTruthy();
  const mapping = (await mappingResponse.json()) as {
    total_pages: number;
    sections: Array<{ title: string; items: unknown[] }>;
  };
  expect(mapping.total_pages).toBe(44);
  expect(mapping.sections.some((section) => section.title === 'Core Documents')).toBeTruthy();
  const mappedItemCount = mapping.sections.reduce((sum, section) => sum + section.items.length, 0);
  expect(mappedItemCount).toBeGreaterThan(0);
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/bundles');
  await expect(page.getByRole('heading', { name: 'Saved bundles' })).toBeVisible();
  const row = page.locator('.bundle-list-row').filter({ hasText: bundle!.name });
  await expect(row).toContainText(bundle!.case_title);
  await expect(row).toContainText('44 pages');
  await expect(row).toContainText(/\d+(\.\d+)? (B|KB|MB)/);
  await expect(row).toContainText(new RegExp(`${bundle!.section_count} section`));
  await assertCaptureReady(page);
  await page.screenshot({ path: '../docs/screenshots/bundles-list-1440.png', fullPage: false });

  await page.goto(`/bundles/${bundle!.id}`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await expect(page.getByRole('heading', { name: bundle!.name })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Bundle Contents' })).toBeVisible();
  await expect(page.locator('ol[aria-label="Bundle document order"] li')).toHaveCount(mappedItemCount);
  await expect(page.getByLabel(/Section for /).first()).toHaveValue('Core Documents');
  await expect(page.getByText('44', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('bundle pages', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Preview PDF' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Download PDF' }).first()).toBeEnabled();
  await page.getByRole('button', { name: 'Preview PDF' }).click();
  await expect(page.getByTestId('pdf-page-canvas')).toBeVisible();
  await expect(page.getByTestId('pdf-page-count')).toHaveText('44');
  await assertCaptureReady(page);
  await page.screenshot({ path: '../docs/screenshots/bundles-detail-1440.png', fullPage: false });
});

test('captures a seeded document with its full accessible title', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await loginToken(page);
  const response = await page.request.get(`${api}/documents?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  const { items } = (await response.json()) as { items: Array<{ id: string; title: string }> };
  const seededDocument = items.find((item) => item.title.length > 0);
  expect(seededDocument).toBeTruthy();
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto(`/documents/${seededDocument!.id}`);
  const title = page.getByRole('heading', { level: 1, name: seededDocument!.title });
  await expect(title).toBeVisible();
  await expect(title).toHaveAttribute('aria-label', seededDocument!.title);
  await expect(title).toHaveAttribute('title', seededDocument!.title);
  await assertCaptureReady(page);
  await page.screenshot({ path: '../docs/screenshots/documents-title-1440.png', fullPage: false });
});

test('research omits an unknown source count instead of showing a placeholder', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await authenticate(page);
  await page.goto('/research');
  await expect(page.getByRole('heading', { name: 'Research Desk' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Retrieved sources' })).toBeVisible();
  await expect(page.locator('.source-count')).toHaveCount(0);
  await expect(page.locator('.sources-card')).not.toContainText('—');
  await assertCaptureReady(page);
  await page.screenshot({ path: '../docs/screenshots/research-count-1440.png', fullPage: false });
});
