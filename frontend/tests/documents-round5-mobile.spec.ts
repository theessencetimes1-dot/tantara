import { execFileSync } from 'node:child_process';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const apiUrl = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;
const screenshots = '../docs/screenshots';

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiUrl}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function openWithToken(page: Page, token: string, href: string) {
  await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
  await page.goto(href);
}

async function captureMobile(page: Page, name: string, drawerOpen = false) {
  const screenshotPath = `${screenshots}/${name}.png`;
  await page.screenshot({ path: screenshotPath });
  const pixelData = execFileSync('python', [
    '-c',
    [
      'from PIL import Image',
      'import json, sys',
      'image = Image.open(sys.argv[1]).convert("RGB")',
      'width, height = image.size',
      'points = [(width - 1, 0), (width - 1, height - 1)] if len(sys.argv) > 2 else [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]',
      'pixels = [image.getpixel(point) for point in points]',
      'print(json.dumps({"size": image.size, "pixels": pixels}))',
    ].join('; '),
    screenshotPath,
    ...(drawerOpen ? ['drawer-open'] : []),
  ]).toString();
  const sampled = JSON.parse(pixelData) as { size: [number, number]; pixels: number[][] };
  expect(sampled.size).toEqual([390, 844]);
  for (const pixel of sampled.pixels) expect(pixel.some((channel) => channel > 32)).toBeTruthy();
}

async function expectPageRatio(page: Page, pageNumber: number) {
  const card = page.locator(`.pdf-page-card[data-page-card="${pageNumber}"]`);
  const ratio = Number(await card.getAttribute('data-page-ratio'));
  const bounds = await card.locator('canvas').boundingBox();
  expect(bounds).not.toBeNull();
  const renderedRatio = bounds!.width / bounds!.height;
  expect(Math.abs(renderedRatio - ratio) / ratio).toBeLessThan(0.01);
}

test('mobile library drawer, cards, viewer geometry, metadata, AI Read and page citation are usable', async ({
  page,
  request,
}) => {
  test.setTimeout(240000);
  await page.setViewportSize({ width: 390, height: 844 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const docsResponse = await request.get(`${apiUrl}/documents?page_size=100`, { headers });
  expect(docsResponse.ok()).toBeTruthy();
  const docsBody = await docsResponse.json();
  const docs = docsBody.items as Array<{
    id: string;
    filename: string;
    is_demo?: boolean;
  }>;
  expect(docs.filter((item) => item.is_demo).length).toBe(8);
  const seededDocument = docs.find((item) => item.filename === 'page-three-motion.pdf');
  expect(seededDocument).toBeTruthy();
  const settings = await request
    .get(`${apiUrl}/settings/ai`, { headers })
    .then((response) => response.json());

  await openWithToken(page, token, '/documents');
  let renderedListResponse: { items: Array<{ id: string }> } | undefined;
  page.on('response', async (response) => {
    if (new URL(response.url()).pathname === '/api/v1/documents' && response.ok()) {
      renderedListResponse = await response.json();
    }
  });
  await page.reload();
  const sidebar = page.locator('.sidebar');
  const main = page.locator('#main');
  const heading = page.getByRole('heading', { name: 'Documents', exact: true });
  await expect(heading).toBeVisible({ timeout: 60000 });
  await expect(page.locator('.documents-mobile-cards .document-card')).toHaveCount(docs.length);
  await expect.poll(() => renderedListResponse?.items.length ?? 0).toBe(docs.length);
  const displayedIds = await page
    .locator('.documents-mobile-cards .document-card')
    .evaluateAll((cards) => cards.map((card) => card.getAttribute('data-document-id')).sort());
  expect(displayedIds).toEqual(renderedListResponse!.items.map((item) => item.id).sort());
  await expect.poll(() => page.evaluate(() => window.document.documentElement.scrollWidth)).toBe(390);
  await expect
    .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0);
  const headingBounds = await heading.boundingBox();
  expect(headingBounds).not.toBeNull();
  expect(headingBounds!.x).toBeGreaterThanOrEqual(0);
  expect(headingBounds!.x + headingBounds!.width).toBeLessThanOrEqual(390);
  const sidebarBounds = await sidebar.boundingBox();
  const mainBounds = await main.boundingBox();
  expect(sidebarBounds).not.toBeNull();
  expect(mainBounds).not.toBeNull();
  expect(
    sidebarBounds!.x < mainBounds!.x + mainBounds!.width &&
      sidebarBounds!.x + sidebarBounds!.width > mainBounds!.x,
  ).toBeFalsy();
  await captureMobile(page, 'documents-round5-library-mobile-390-real');

  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(sidebar).toHaveClass(/open/);
  await expect
    .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().x))
    .toBeGreaterThanOrEqual(0);
  const drawerDocumentLink = page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Documents', exact: true });
  await expect(drawerDocumentLink).toBeVisible();
  const drawerBounds = await sidebar.boundingBox();
  expect(drawerBounds).not.toBeNull();
  expect(drawerBounds!.x).toBeGreaterThanOrEqual(0);
  expect(drawerBounds!.x + drawerBounds!.width).toBeLessThanOrEqual(390);
  await expect(page.locator('.sidebar-backdrop')).toBeVisible();
  await captureMobile(page, 'documents-round6-drawer-open-mobile-390-real', true);
  await page.locator('.sidebar-backdrop').click({ position: { x: 350, y: 400 } });
  await expect
    .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0);
  await expect(heading).toBeVisible();
  await captureMobile(page, 'documents-round6-drawer-dismissed-mobile-390-real');
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Documents', exact: true })
    .click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.locator('.sidebar-backdrop')).toHaveCount(0);
  await expect(heading).toBeVisible();
  await expect
    .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0);
  await captureMobile(page, 'documents-round6-drawer-after-navigation-mobile-390-real');
  const documentLink = page
    .locator('.documents-mobile-cards')
    .getByRole('link', { name: 'Page Three Motion' });
  await documentLink.click();
  await expect(page).toHaveURL(new RegExp(`/documents/${seededDocument!.id}$`));
  await expect(page.getByLabel('PDF page 1')).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await expect(page.getByText('Loading PDF pages…')).toHaveCount(0);
  await expect(page.getByLabel('Jump to page')).toHaveValue('1');
  await expectPageRatio(page, 1);
  await expect.poll(() => page.evaluate(() => window.document.documentElement.scrollWidth)).toBe(390);
  await captureMobile(page, 'documents-round5-viewer-mobile-390-real');

  await page.locator('.document-metadata').scrollIntoViewIfNeeded();
  await expect(page.getByRole('group', { name: /^Filename / })).toBeVisible();
  await expect(page.locator('.document-metadata')).toContainText('Jurisdiction India');
  await captureMobile(page, 'documents-round5-metadata-mobile-390-real');

  if (settings.runtime_status?.reachable) {
    await page.getByRole('button', { name: 'Run document extraction' }).click();
    await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible({ timeout: 150000 });
    await expect(page.locator('.ai-read-field').first()).toBeVisible({ timeout: 150000 });
    const arbitrationClause = page.locator('.ai-read-field[data-field-key="arbitration_clause"]');
    const summary = page.locator('.ai-read-field[data-field-key="summary"]');
    await expect(arbitrationClause).toBeVisible();
    await expect(summary).toContainText('Routine procedural filing');
    await expect(summary).toContainText('Local text extraction');
    await expect(summary).toContainText('candidate only');
    await arbitrationClause.scrollIntoViewIfNeeded();
    await expect(arbitrationClause).toBeVisible();
    const summaryLabel = summary.locator('> strong');
    const summaryLabelBounds = await summaryLabel.boundingBox();
    expect(summaryLabelBounds).not.toBeNull();
    expect(summaryLabelBounds!.height).toBeLessThanOrEqual(40);
    const summaryDisclosure = summary.locator('.ai-read-summary-disclosure');
    const collapsedHeight = await summaryDisclosure.boundingBox();
    expect(collapsedHeight).not.toBeNull();
    expect(collapsedHeight!.height).toBeLessThanOrEqual(160);
    await summaryDisclosure.locator('summary').click();
    await expect(summaryDisclosure).toContainText(/Unique page three clause/);
    await summaryDisclosure.locator('summary').click();
    await arbitrationClause.scrollIntoViewIfNeeded();
    await expect(summary).toBeVisible();
    await captureMobile(page, 'documents-round5-airead-mobile-390-populated-real');
  } else {
    await page.getByRole('button', { name: 'Run document extraction' }).click();
    await expect(page.locator('[data-error-category="model_unavailable"]')).toBeVisible();
    await expect(page.locator('.ai-read-field')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText(/https?:\/\/|:\d{2,5}/);
    await captureMobile(page, 'documents-round5-airead-mobile-390-unavailable-real');
  }

  await page.locator('.document-page-text-list summary').click();
  await page.locator('.document-page-text-list .document-page-citation').getByText('Page 3').click();
  await expect(page).toHaveURL(/page=3/);
  await expect(page.getByLabel('Jump to page')).toHaveValue('3', { timeout: 60000 });
  await expect(page.getByLabel('PDF page 3')).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel('PDF page 3')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await expect(page.locator('#page-3')).toContainText(
    /Unique page three clause: Sapphire Pavilion shall host the special procedural conference/,
  );
  await expect(page.locator('.pdf-page-card[data-page-card="3"] .pdf-text-layer')).toContainText(
    /Unique page three clause/,
  );
  const citationToolbarBounds = await page.locator('.pdf-toolbar').boundingBox();
  const citationLabelBounds = await page
    .locator('.pdf-page-card[data-page-card="3"] .pdf-page-label')
    .boundingBox();
  expect(citationToolbarBounds).not.toBeNull();
  expect(citationLabelBounds).not.toBeNull();
  const citationOffset = citationLabelBounds!.y - citationToolbarBounds!.y - citationToolbarBounds!.height;
  expect(citationOffset).toBeGreaterThanOrEqual(0);
  expect(citationOffset).toBeLessThanOrEqual(150);
  await expectPageRatio(page, 3);
  await captureMobile(page, 'documents-round5-citation-page3-mobile-390-real');

  await page.goto('/search');
  await page.getByRole('textbox', { name: 'Search documents' }).fill('agreement');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.locator('.search-hit').first()).toBeVisible({ timeout: 60000 });
  await expect(page.locator('.search-hit').first()).not.toContainText('Untitled document');
  await expect.poll(() => page.evaluate(() => window.document.documentElement.scrollWidth)).toBe(390);
  await expect
    .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0);
  await captureMobile(page, 'documents-round5-search-mobile-390-real');
});

test('mobile empty and local extraction fallback settle with navigation closed', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 390, height: 844 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const documentsResponse = await request.get(`${apiUrl}/documents?page_size=100`, { headers });
  expect(documentsResponse.ok()).toBeTruthy();
  const documents = (await documentsResponse.json()).items as Array<{ id: string; filename: string }>;
  const documentCount = documents.length;
  const seededDocument = documents.find((document) => document.filename === 'page-three-motion.pdf');
  expect(seededDocument).toBeTruthy();
  const sidebar = page.locator('.sidebar');
  const main = page.locator('#main');
  const assertNavigationClosed = async () => {
    await expect
      .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().right))
      .toBeLessThanOrEqual(0);
    const sidebarBounds = await sidebar.boundingBox();
    const mainBounds = await main.boundingBox();
    expect(sidebarBounds).not.toBeNull();
    expect(mainBounds).not.toBeNull();
    expect(
      sidebarBounds!.x < mainBounds!.x + mainBounds!.width &&
        sidebarBounds!.x + sidebarBounds!.width > mainBounds!.x,
    ).toBeFalsy();
  };

  await openWithToken(page, token, '/documents');
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible({ timeout: 60000 });
  await assertNavigationClosed();
  await page.getByRole('textbox', { name: 'Search documents' }).fill('no-match-round5-69428');
  await expect(page.getByRole('heading', { name: '0 matching documents' })).toBeVisible();
  await expect(page.locator('.documents-library-toolbar')).toContainText('0 matching documents');
  await captureMobile(page, 'documents-round5-empty-mobile-390-real');
  await page.getByRole('textbox', { name: 'Search documents' }).fill('');
  await expect(page.locator('.documents-mobile-cards .document-card')).toHaveCount(documentCount);
  await expect(page.locator('.documents-library-toolbar')).toContainText(`${documentCount} documents`);

  const originalSettings = await request
    .get(`${apiUrl}/settings/ai`, { headers })
    .then((response) => response.json());
  try {
    await request.patch(`${apiUrl}/settings/ai`, {
      headers,
      data: { base_url: 'http://127.0.0.1:9/v1', model: originalSettings.model },
    });
    const deadSettings = await request
      .get(`${apiUrl}/settings/ai`, { headers })
      .then((response) => response.json());
    expect(deadSettings.runtime_status?.reachable).toBeFalsy();
    await openWithToken(page, token, `/documents/${seededDocument!.id}`);
    await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', { timeout: 60000 });
    await assertNavigationClosed();
    await page.getByRole('button', { name: 'Run document extraction' }).click();
    await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible({ timeout: 60000 });
    await expect(page.locator('.ai-read-field').first()).toBeVisible();
    await expect(page.locator('.ai-read-panel')).toContainText('Local text extraction');
    await expect(page.locator('.ai-read-panel')).toContainText('candidate only');
    await expect(page.locator('body')).not.toContainText(/https?:\/\/|:\d{2,5}/);
    await captureMobile(page, 'documents-round5-ai-read-unavailable-mobile-390-real');
  } finally {
    await request.patch(`${apiUrl}/settings/ai`, {
      headers,
      data: { base_url: originalSettings.base_url, model: originalSettings.model },
    });
  }
});
