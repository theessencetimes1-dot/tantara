import { readFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { documentHref } from '../src/features/documents/links';

const apiUrl = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;
const uploadedDocuments: Array<{ id: string; token: string }> = [];

test.afterEach(async ({ request }) => {
  for (const { id, token } of uploadedDocuments.splice(0)) {
    const response = await request.delete(`${apiUrl}/documents/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.ok()).toBeTruthy();
  }
});

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiUrl}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function uploadFixture(request: APIRequestContext, fixtureName: string) {
  const token = await signIn(request);
  const response = await request.post(`${apiUrl}/documents/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      file: {
        name: fixtureName,
        mimeType: 'application/pdf',
        buffer: readFileSync(`tests/fixtures/${fixtureName}`),
      },
      title: fixtureName,
    },
  });
  expect(response.status()).toBe(202);
  const uploaded = await response.json();
  uploadedDocuments.push({ id: uploaded.document_id as string, token });
  await expect
    .poll(
      async () => {
        const job = await request.get(`${apiUrl}/documents/${uploaded.document_id}/job`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        return (await job.json()).status;
      },
      { timeout: 60000 },
    )
    .toBe('ready');
  return { documentId: uploaded.document_id as string, token };
}

async function openWithToken(page: Page, token: string, href: string) {
  await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
  await page.goto(href);
}

test('document URL builder encodes identifiers and preserves citation pages', () => {
  expect(documentHref('contract/one', 2)).toBe('/documents/contract%2Fone?page=2');
  expect(documentHref('contract-1')).toBe('/documents/contract-1');
});

test('captures seeded document and search states before fixture uploads', async ({ page, request }) => {
  test.setTimeout(90000);
  const token = await signIn(request);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openWithToken(page, token, '/documents');
  await expect(page.locator('.documents-table tbody tr').first()).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: 'test-results/documents-library-desktop-1440-real.png' });
  const documentsResponse = await request.get(`${apiUrl}/documents?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(documentsResponse.ok()).toBeTruthy();
  const documents = (await documentsResponse.json()).items as Array<{
    id: string;
    filename: string;
    title: string;
    is_demo: boolean;
  }>;
  const seededPdf = documents.find((document) => document.filename === 'page-three-motion.pdf');
  expect(seededPdf).toBeTruthy();
  expect(seededPdf!.is_demo).toBeTruthy();
  await page.goto(`/documents/${seededPdf!.id}`);
  await expect(page.getByRole('heading', { name: seededPdf!.title })).toBeVisible();
  await expect(page.locator('.pdf-page-surface canvas').first()).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await page.screenshot({ path: 'test-results/documents-seeded-viewer-desktop-1440-real.png' });
  await page.goto('/documents');
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });

  await page.getByRole('textbox', { name: 'Search documents' }).fill('no-document-with-this-title-9472');
  await expect(page.getByRole('heading', { name: '0 matching documents' })).toBeVisible();
  await expect(page.getByLabel('Filter by status')).toHaveValue('');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: 'test-results/documents-library-empty-desktop-1440-real.png',
  });

  await page.goto('/search');
  await page.getByRole('textbox', { name: 'Search documents' }).fill('agreement');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.locator('.search-hit').first()).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.search-hit').first()).not.toContainText('Untitled document');
  await expect(page.getByText(/fusion rank score.*not a confidence value/i)).toBeVisible();
  await page.screenshot({
    path: 'test-results/documents-search-desktop-1440-real.png',
  });
});

test('uploaded multi-page PDF deep-link scrolls to and highlights page 2', async ({ page, request }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const { documentId, token } = await uploadFixture(request, 'arbitration-text-layer.pdf');
  await openWithToken(page, token, documentHref(documentId, 2));
  const targetPage = page.locator('.pdf-page-card[data-page-card="2"]');
  await expect(targetPage).toBeVisible({ timeout: 30000 });
  await expect(targetPage).toHaveClass(/pdf-page-deep-link/);
  const pageCanvas = targetPage.getByLabel('PDF page 2');
  await expect(pageCanvas).toBeVisible({ timeout: 45000 });
  await expect(pageCanvas).toHaveAttribute('data-rendered', 'true', { timeout: 45000 });
  await expect(pageCanvas).toHaveJSProperty('tagName', 'CANVAS');
  await expect
    .poll(() =>
      targetPage.evaluate((node) => {
        const bounds = node.getBoundingClientRect();
        const viewport = node.closest('.pdf-pages-scroll')?.getBoundingClientRect();
        return Boolean(viewport && bounds.top < viewport.bottom && bounds.bottom > viewport.top);
      }),
    )
    .toBeTruthy();
  const sidebar = page.locator('.sidebar');
  const header = page.locator('.topbar');
  const canvas = pageCanvas;
  await expect.poll(() => sidebar.evaluate((node) => Math.round(node.getBoundingClientRect().left))).toBe(0);
  await expect
    .poll(async () => {
      const headerBottom = await header.evaluate((node) => node.getBoundingClientRect().bottom);
      const canvasTop = await canvas.evaluate((node) => node.getBoundingClientRect().top);
      return canvasTop > headerBottom;
    })
    .toBeTruthy();
  const skipLinkBounds = await page.locator('.skip-link').boundingBox();
  const mainBounds = await page.locator('#main').boundingBox();
  expect(skipLinkBounds).not.toBeNull();
  expect(mainBounds).not.toBeNull();
  expect(skipLinkBounds!.y + skipLinkBounds!.height).toBeLessThanOrEqual(0);
  expect(mainBounds!.x).toBeGreaterThan(0);
  await page.screenshot({
    path: 'test-results/documents-viewer-page2-desktop-1440-real.png',
  });
  const mobilePage = await page.context().newPage();
  await mobilePage.setViewportSize({ width: 390, height: 844 });
  await openWithToken(mobilePage, token, documentHref(documentId, 2));
  const mobilePageTwo = mobilePage.locator('.pdf-page-card[data-page-card="2"]');
  await expect(mobilePageTwo).toBeVisible({ timeout: 45000 });
  await expect(mobilePageTwo.getByLabel('PDF page 2')).toBeVisible({ timeout: 45000 });
  await expect(mobilePageTwo.getByLabel('PDF page 2')).toHaveAttribute('data-rendered', 'true', {
    timeout: 45000,
  });
  await expect
    .poll(() => mobilePage.locator('.sidebar').evaluate((node) => node.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0);
  await expect
    .poll(() =>
      mobilePage.locator('.topbar').evaluate((node) => Math.round(node.getBoundingClientRect().top)),
    )
    .toBe(0);
  await mobilePage.close();
});

test('viewer metadata uses separated definition rows and an accessible copy confirmation', async ({
  page,
  request,
  context,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const documents = await request.get(`${apiUrl}/documents`, { headers }).then((response) => response.json());
  const document = documents.items.find(
    (item: { filename: string }) => item.filename === 'page-three-motion.pdf',
  );
  expect(document).toBeTruthy();
  await openWithToken(page, token, `/documents/${document.id}`);
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], {
    origin: new URL(page.url()).origin,
  });
  await expect(page.getByRole('group', { name: 'Filename page-three-motion.pdf' })).toHaveText(
    /Filename\s+page-three-motion\.pdf/,
  );
  await expect(page.getByRole('group', { name: 'Pages 5' })).toHaveText(/Pages\s+5/);
  await expect(page.getByRole('group', { name: /^Characters / })).toHaveText(/Characters\s+[\d,]+/);
  await expect(page.getByRole('group', { name: /^Created / })).toHaveText(/Created\s+.+/);
  await expect(page.getByRole('group', { name: /^Jurisdiction / })).toHaveText(/Jurisdiction\s+.+/);
  const copyButton = page.getByRole('button', { name: 'Copy SHA-256' });
  await expect(copyButton).toBeVisible();
  await copyButton.click();
  await expect(page.getByRole('status').filter({ hasText: 'SHA-256 copied' })).toBeVisible();
});

test('page-aware chunks find SIAC Rules and open highlighted PDF page 2', async ({ page, request }) => {
  const { documentId, token } = await uploadFixture(request, 'arbitration-text-layer.pdf');
  await openWithToken(page, token, `/documents/${documentId}`);
  await page.getByLabel('Search this document').fill('SIAC Rules');
  await page.getByRole('button', { name: 'Find chunks' }).click();
  const pageTwoHit = page.locator('.citation-chunk').filter({ hasText: 'Page 2' });
  await expect(pageTwoHit).toBeVisible({ timeout: 30000 });
  await expect(pageTwoHit.getByText(/Relevance\s+\d/)).toBeVisible();
  await pageTwoHit.getByRole('link', { name: 'Open page 2' }).click();
  await expect(page).toHaveURL(/page=2/);
  const pageTwo = page.locator('.pdf-page-card[data-page-card="2"]');
  await expect(pageTwo).toHaveClass(/pdf-page-deep-link/);
  await expect(pageTwo.locator('canvas')).toHaveAttribute('aria-label', 'PDF page 2');
});

test('AI Read renders real API fields and persists an edited field after reload', async ({
  page,
  request,
}) => {
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const documents = await request.get(`${apiUrl}/documents`, { headers }).then((response) => response.json());
  const document = documents.items.find(
    (item: { filename: string; status: string }) =>
      item.filename === 'page-three-motion.pdf' && item.status === 'ready',
  );
  expect(document).toBeTruthy();
  await openWithToken(page, token, `/documents/${document.id}`);
  await page.getByRole('button', { name: 'Run document extraction' }).click();
  await expect(page.locator('.ai-read-field').first()).toBeVisible();
  const clauseField = page.locator('.ai-read-field[data-field-key="arbitration_clause"]');
  await expect(clauseField).toContainText('Not extracted');
  await expect(page.locator('.ai-read-field[data-field-key="summary"]')).toContainText(
    'Routine procedural filing',
  );
  await page.getByRole('button', { name: 'Edit document_type' }).click();
  await page.getByRole('textbox', { name: 'Edit document_type' }).fill('Reviewed arbitration agreement');
  await page.getByRole('button', { name: 'Save document_type' }).click();
  await expect(page.locator('.ai-read-field[data-provenance-key="extracted_reviewed"]')).toContainText(
    'Reviewed extraction',
  );
  await page.reload();
  await expect(page.locator('.ai-read-field').filter({ hasText: 'document type' })).toContainText(
    'Reviewed arbitration agreement',
  );
  await expect(page.locator('.pdf-viewer canvas').first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText('Loading PDF pages…')).toHaveCount(0);
  await expect(page.locator('.ai-read-field').filter({ hasText: 'document type' })).toContainText(
    'Reviewed extraction',
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: 'test-results/documents-ai-read-success-desktop-1440-real.png',
  });
});

test('scanned fixture yields OCR text and reports the job warnings', async ({ request }) => {
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const documents = await request.get(`${apiUrl}/documents`, { headers }).then((response) => response.json());
  const document = documents.items.find(
    (item: { filename: string }) => item.filename === 'scanned-agreement.pdf',
  );
  expect(document).toBeTruthy();
  const documentId = document.id as string;
  const response = await request.get(`${apiUrl}/documents/${documentId}/pages`, { headers });
  const pages = (await response.json()).pages as Array<{ text: string; warnings: string[] }>;
  const extractedOcrQuote = pages[0].text.toUpperCase();
  expect(extractedOcrQuote).toContain('ARBITRATION AGREEMENT');
  const job = await request
    .get(`${apiUrl}/documents/${documentId}/job`, { headers })
    .then((result) => result.json());
  expect(Array.isArray(job.warnings)).toBeTruthy();
  expect(pages[0].warnings).toEqual(expect.any(Array));
  expect(job.warnings).toEqual(expect.any(Array));
});

test('viewer formats structured page warnings from real ingestion', async ({ page, request }) => {
  const { documentId, token } = await uploadFixture(request, 'blank-page-review.pdf');
  const headers = { Authorization: `Bearer ${token}` };
  const pagesResponse = await request.get(`${apiUrl}/documents/${documentId}/pages`, { headers });
  expect(pagesResponse.ok()).toBeTruthy();
  const pages = (await pagesResponse.json()).pages as Array<{
    warnings: Array<string | { page?: number; warning: string }>;
  }>;
  expect(pages[1].warnings).toContainEqual({
    page: 2,
    warning: 'No usable text; manual review required',
  });
  await openWithToken(page, token, `/documents/${documentId}`);
  await expect(page.getByRole('note').getByText('Extraction warnings')).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Page 2: No usable text; manual review required');
});

test('local extraction is honest and works independently of the configured model', async ({
  page,
  request,
}) => {
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const original = await request
    .get(`${apiUrl}/settings/ai`, { headers })
    .then((response) => response.json());
  const docs = await request.get(`${apiUrl}/documents`, { headers }).then((response) => response.json());
  const sourceDocument = docs.items.find(
    (item: { status: string; filename: string }) =>
      item.status === 'ready' && item.filename === 'scanned-agreement.pdf',
  );
  expect(sourceDocument).toBeTruthy();
  await request.patch(`${apiUrl}/settings/ai`, { headers, data: { base_url: 'http://127.0.0.1:9/v1' } });
  try {
    await openWithToken(page, token, `/documents/${sourceDocument.id}`);
    await page.getByRole('button', { name: /Run document extraction|Run again/ }).click();
    await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible();
    await expect(page.locator('.ai-read-field').first()).toBeVisible();
    await expect(page.locator('.ai-read-panel')).toContainText('Local text extraction');
    await expect(page.locator('.ai-read-panel')).toContainText('candidate only');
    await expect(page.locator('.ai-read-panel')).not.toContainText('AI-generated');
    await expect(page.locator('body')).not.toContainText(/https?:\/\/|127\.0\.0\.1|:\d{2,5}/);
  } finally {
    await request.patch(`${apiUrl}/settings/ai`, { headers, data: { base_url: original.base_url } });
  }
});
