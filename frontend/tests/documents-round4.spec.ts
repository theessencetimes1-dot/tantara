import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const apiUrl = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;
const screenshots = 'test-results';
const liveModelBase = 'http://192.168.0.101:8080/v1';
const liveModelName = 'MiniCPM5-2B';

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiUrl}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function getSeededPdf(request: APIRequestContext, token: string) {
  const response = await request.get(`${apiUrl}/documents`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const documents = (await response.json()).items as Array<{
    id: string;
    filename: string;
    page_count?: number;
    status: string;
    is_demo?: boolean;
  }>;
  const pdf = documents.find(
    (document) =>
      document.status === 'ready' &&
      document.is_demo &&
      (document.page_count ?? 0) > 1 &&
      document.filename === 'page-three-motion.pdf',
  );
  expect(pdf).toBeTruthy();
  return pdf!;
}

async function openWithToken(page: Page, token: string, href: string) {
  await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
  await page.goto(href);
}

async function waitForViewer(page: Page, requestedPage = 1) {
  await expect(page.getByLabel('Jump to page')).toHaveValue(String(requestedPage), {
    timeout: 60000,
  });
  await expect(page.getByLabel(`PDF page ${requestedPage}`)).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel(`PDF page ${requestedPage}`)).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await expect(page.getByText('Loading PDF pages…')).toHaveCount(0);
}

test('workspace shell, skip link, metadata, and PDF page controls are stable on direct viewer entry', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const token = await signIn(request);
  const document = await getSeededPdf(request, token);
  const pageCount = document.page_count ?? 1;
  const targetPage = Math.min(2, pageCount);

  await page.setViewportSize({ width: 1440, height: 900 });
  await openWithToken(page, token, `/documents/${document.id}?page=${targetPage}`);
  await waitForViewer(page, targetPage);

  const shellHeader = page.locator('.topbar');
  const shellSidebar = page.locator('.sidebar');
  const shellMain = page.locator('.main');
  const pageContent = page.locator('.document-detail-page');
  const toolbar = page.locator('.pdf-toolbar');
  const canvas = page.getByLabel(`PDF page ${targetPage}`);
  const viewerScroll = page.locator('.pdf-pages-scroll');

  await expect
    .poll(() => shellHeader.evaluate((element) => Math.round(element.getBoundingClientRect().top)))
    .toBe(0);
  await expect
    .poll(() => shellSidebar.evaluate((element) => Math.round(element.getBoundingClientRect().left)))
    .toBe(0);
  await expect
    .poll(async () => {
      const headerBounds = await shellHeader.boundingBox();
      const contentBounds = await pageContent.boundingBox();
      return Boolean(
        headerBounds && contentBounds && contentBounds.y >= headerBounds.y + headerBounds.height,
      );
    })
    .toBeTruthy();
  await expect(toolbar).toBeInViewport();
  await expect(page.getByLabel('Jump to page')).toBeInViewport();
  await expect
    .poll(async () => {
      const headerBounds = await shellHeader.boundingBox();
      const toolbarBounds = await toolbar.boundingBox();
      return Boolean(
        headerBounds && toolbarBounds && toolbarBounds.y >= headerBounds.y + headerBounds.height,
      );
    })
    .toBeTruthy();
  await expect
    .poll(async () => {
      const canvasBounds = await canvas.boundingBox();
      const scrollBounds = await viewerScroll.boundingBox();
      return Boolean(
        canvasBounds &&
        scrollBounds &&
        canvasBounds.x >= scrollBounds.x &&
        canvasBounds.x + canvasBounds.width <= scrollBounds.x + scrollBounds.width + 1,
      );
    })
    .toBeTruthy();
  await expect(page.getByRole('group', { name: new RegExp(`Pages ${pageCount}`) })).toBeVisible();
  await expect(page.getByRole('group', { name: /^AI review / })).toBeVisible();

  const skipLink = page.locator('.skip-link');
  const hiddenSkipBounds = await skipLink.boundingBox();
  expect(hiddenSkipBounds).not.toBeNull();
  expect(hiddenSkipBounds!.y + hiddenSkipBounds!.height).toBeLessThanOrEqual(0);
  await page.keyboard.press('Tab');
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeInViewport();
  await page.keyboard.press('Tab');
  await expect(skipLink).not.toBeFocused();

  await page.evaluate(() => window.scrollTo(0, window.document.body.scrollHeight));
  await expect
    .poll(() => shellHeader.evaluate((element) => Math.round(element.getBoundingClientRect().top)))
    .toBe(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${screenshots}/documents-viewer-page${targetPage}-desktop-1440-real.png`,
  });
  await openWithToken(page, token, '/documents');
  await expect(page.locator('.documents-table tbody tr').first()).toBeVisible({ timeout: 30000 });
  const pdfRow = page.locator('.documents-table tbody tr').filter({ hasText: document.filename });
  await expect(pdfRow).toBeVisible();
  await pdfRow.locator('td').nth(1).click();
  const previewCanvas = page.locator('.document-preview-pane canvas');
  await expect(previewCanvas).toBeVisible({ timeout: 60000 });
  await expect(previewCanvas).toHaveAttribute('data-rendered', 'true', { timeout: 60000 });
  await page.getByLabel('Filter by status').selectOption('failed');
  await expect(page.getByLabel('Filter by status')).toHaveValue('');
  await expect(page.locator('.documents-table tbody tr').first()).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: `${screenshots}/documents-library-desktop-1440.png` });
  await page.getByRole('textbox', { name: 'Search documents' }).fill('no-match-round4-77291');
  await expect(page.getByRole('heading', { name: '0 matching documents' })).toBeVisible();
  await expect(page.getByLabel('Filter by status')).toHaveValue('');
  await page.screenshot({ path: `${screenshots}/documents-library-empty-desktop-1440.png` });
});

test('reachable model settings do not relabel local extraction as model generated', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const document = await getSeededPdf(request, token);
  const originalSettings = await request
    .get(`${apiUrl}/settings/ai`, { headers })
    .then((response) => response.json());
  await request.patch(`${apiUrl}/settings/ai`, {
    headers,
    data: { base_url: liveModelBase, model: liveModelName },
  });
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openWithToken(page, token, `/documents/${document.id}`);
    await waitForViewer(page, 1);
    await expect(page.getByRole('button', { name: 'Run document extraction' })).toBeVisible();
    const settings = await request
      .get(`${apiUrl}/settings/ai`, { headers })
      .then((response) => response.json());
    await page.getByRole('button', { name: /Run document extraction|Run again/ }).click();
    if (settings.runtime_status?.reachable) {
      await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible({ timeout: 120000 });
      await expect(page.locator('.ai-read-field').first()).toBeVisible({ timeout: 120000 });
    } else {
      await expect(page.locator('[data-error-category="model_unavailable"]')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('.ai-read-field')).toHaveCount(0);
      return;
    }
    await expect(page.locator('.pdf-viewer canvas').first()).toBeVisible({ timeout: 60000 });
    await expect(page.getByText('Loading PDF pages…')).toHaveCount(0);
    await expect(page.locator('.ai-read-panel')).not.toContainText(/ai_suggested/);
    await expect(page.locator('.ai-read-panel')).toContainText('Local text extraction · candidate only');
    await expect(page.locator('.ai-read-panel')).toContainText('Not extracted');
    await expect(page.locator('.ai-read-field[data-field-key="arbitration_clause"]')).toContainText(
      'Not extracted',
    );
    await expect(page.locator('.ai-read-panel')).not.toContainText(/\[\]|\{"found"/);
    await expect(page.locator('.ai-read-field[data-field-key="arbitration_clause"]')).toContainText(
      'Not extracted',
    );
    await expect(page.locator('.ai-read-panel .ai-source-page').first()).toBeVisible();
    await page.screenshot({
      path: `${screenshots}/documents-ai-read-success-desktop-1440-real.png`,
    });
  } finally {
    await request.patch(`${apiUrl}/settings/ai`, {
      headers,
      data: { base_url: originalSettings.base_url, model: originalSettings.model },
    });
  }
});

test('local extraction remains labeled as candidate text when model is unavailable', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const document = await getSeededPdf(request, token);
  const originalSettings = await request
    .get(`${apiUrl}/settings/ai`, { headers })
    .then((response) => response.json());
  await request.patch(`${apiUrl}/settings/ai`, {
    headers,
    data: { base_url: 'http://127.0.0.1:9/v1', model: originalSettings.model },
  });
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openWithToken(page, token, `/documents/${document.id}`);
    await waitForViewer(page, 1);
    await page.getByRole('button', { name: 'Run document extraction' }).click();
    await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible({ timeout: 30000 });
    await expect(page.locator('.ai-read-field').first()).toBeVisible();
    await expect(page.locator('.ai-read-panel')).toContainText('Local text extraction');
    await expect(page.locator('.ai-read-panel')).toContainText('candidate only');
    await expect(page.locator('.ai-read-panel')).not.toContainText('AI-generated');
    await expect(page.locator('body')).not.toContainText(/https?:\/\/|127\.0\.0\.1|192\.168\.|:\d{2,5}/);
    await page.screenshot({
      path: `${screenshots}/documents-ai-read-local-candidate-desktop-1440.png`,
    });
  } finally {
    await request.patch(`${apiUrl}/settings/ai`, {
      headers,
      data: { base_url: originalSettings.base_url, model: originalSettings.model },
    });
  }
});
