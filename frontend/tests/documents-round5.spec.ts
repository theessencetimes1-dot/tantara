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

async function seededPageThreeDocument(request: APIRequestContext, token: string) {
  const response = await request.get(`${apiUrl}/documents?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  const documents = (await response.json()).items as Array<{
    id: string;
    filename: string;
    content_hash: string;
    page_count: number;
    status: string;
    is_demo: boolean;
  }>;
  const document = documents.find((item) => item.filename === 'page-three-motion.pdf');
  expect(document).toBeTruthy();
  expect(document!.status).toBe('ready');
  expect(document!.is_demo).toBeTruthy();
  return document!;
}

async function captureViewport(page: Page, name: string, width: number, height: number) {
  const screenshotPath = `${screenshots}/${name}.png`;
  await page.screenshot({ path: screenshotPath });
  const pixelData = execFileSync('python', [
    '-c',
    [
      'from PIL import Image',
      'import json, sys',
      'image = Image.open(sys.argv[1]).convert("RGB")',
      'width, height = image.size',
      'points = [(width - 1, 0), (width - 1, height - 1), (min(250, width - 1), 0), (min(250, width - 1), height - 1)]',
      'pixels = [image.getpixel(point) for point in points]',
      'print(json.dumps({"size": image.size, "pixels": pixels}))',
    ].join('; '),
    screenshotPath,
  ]).toString();
  const sampled = JSON.parse(pixelData) as { size: [number, number]; pixels: number[][] };
  expect(sampled.size).toEqual([width, height]);
  for (const pixel of sampled.pixels) {
    expect(pixel.some((channel) => channel > 32)).toBeTruthy();
  }
}

async function expectPageRatio(page: Page, pageNumber: number) {
  const pageCard = page.locator(`.pdf-page-card[data-page-card="${pageNumber}"]`);
  const ratioData = await pageCard.getAttribute('data-page-ratio');
  const canvas = pageCard.locator('canvas');
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  const sourceRatio = Number(ratioData);
  const renderedRatio = bounds!.width / bounds!.height;
  expect(Math.abs(renderedRatio - sourceRatio) / sourceRatio).toBeLessThan(0.01);
}

test('real seeded document opens from library, renders proportionally, reads, and follows page citations', async ({
  page,
  request,
}) => {
  test.setTimeout(240000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const settingsResponse = await request.get(`${apiUrl}/settings/ai`, { headers });
  expect(settingsResponse.ok()).toBeTruthy();
  let settings = await settingsResponse.json();
  if (!settings.runtime_status?.reachable) {
    await request.patch(`${apiUrl}/settings/ai`, {
      headers,
      data: { base_url: 'http://192.168.0.101:8080/v1', model: settings.model },
    });
    settings = await request.get(`${apiUrl}/settings/ai`, { headers }).then((response) => response.json());
  }
  const configuredModel = settings.runtime_status?.model ?? settings.model;
  const document = await seededPageThreeDocument(request, token);
  await openWithToken(page, token, '/documents');
  await expect(page.getByRole('link', { name: 'Page Three Motion' })).toBeVisible({ timeout: 60000 });
  await page.getByRole('link', { name: 'Page Three Motion' }).click();
  await expect(page).toHaveURL(new RegExp(`/documents/${document.id}$`));
  await expect(page.getByLabel('PDF page 1')).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await expect(page.getByText('Loading PDF pages…')).toHaveCount(0);
  await expect(page.getByLabel('Jump to page')).toHaveValue('1');
  await expectPageRatio(page, 1);
  await expect(page.getByRole('group', { name: /^Filename / })).toContainText('page-three-motion.pdf');
  await expect(page.getByRole('group', { name: /^Pages 5$/ })).toHaveText('Pages 5');
  await expect(page.getByRole('group', { name: /^Characters / })).toContainText('Characters ');
  await expect(page.locator('.document-metadata')).toContainText('Jurisdiction India');
  await expect(page.locator('.document-metadata')).toContainText('SHA-256');
  await captureViewport(page, 'documents-round5-viewer-desktop-1440-real', 1440, 900);

  await page.locator('.document-metadata').scrollIntoViewIfNeeded();
  await expect(page.getByRole('group', { name: /^Filename / })).toBeVisible();
  await captureViewport(page, 'documents-round5-metadata-desktop-1440-real', 1440, 900);

  await expect(page.getByRole('button', { name: 'Run document extraction' })).toBeVisible();
  await page.getByRole('button', { name: 'Run document extraction' }).click();
  await expect(page.getByRole('button', { name: 'Run again' })).toBeVisible({ timeout: 150000 });
  await expect(page.locator('.ai-read-field').first()).toBeVisible({ timeout: 150000 });
  await expect(page.locator('.ai-read-field[data-field-key="summary"]')).toContainText(
    'Routine procedural filing',
  );
  await expect(page.locator('.ai-read-panel')).toContainText('Local text extraction');
  await expect(page.locator('.ai-read-panel')).toContainText('candidate only');
  if (configuredModel) await expect(page.locator('.ai-read-panel')).toContainText(configuredModel);
  await expect(page.locator('.ai-read-panel')).not.toContainText(/\[\]|\{"found"|ai_suggested/);
  await expect(page.locator('.ai-read-panel')).not.toContainText('AI-generated');
  const arbitrationClause = page.locator('.ai-read-field[data-field-key="arbitration_clause"]');
  const extractedSummary = page.locator('.ai-read-field[data-field-key="summary"]');
  await expect(arbitrationClause).toBeVisible();
  await expect(extractedSummary).toBeVisible();
  await expect(arbitrationClause).toContainText('Not extracted');
  const aiPanel = page.locator('.ai-read-panel');
  const panelBounds = await aiPanel.boundingBox();
  expect(panelBounds).not.toBeNull();
  expect(panelBounds!.y + panelBounds!.height).toBeLessThanOrEqual(900);
  const fieldList = page.locator('.ai-read-fields');
  await fieldList.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(page.locator('.ai-read-field').last()).toBeVisible();
  await fieldList.evaluate((element) => {
    element.scrollTop = 0;
  });
  const summaryDisclosure = extractedSummary.locator('.ai-read-summary-disclosure');
  const collapsedSummaryHeight = await summaryDisclosure.boundingBox();
  expect(collapsedSummaryHeight).not.toBeNull();
  expect(collapsedSummaryHeight!.height).toBeLessThanOrEqual(160);
  await summaryDisclosure.locator('summary').click();
  await expect(summaryDisclosure).toContainText(/Unique page three clause/);
  await summaryDisclosure.locator('summary').click();
  await page.getByRole('button', { name: 'Zoom out' }).click();
  await page.getByRole('button', { name: 'Zoom out' }).click();
  await page.getByRole('button', { name: 'Zoom out' }).click();
  await expect(page.locator('.pdf-zoom-controls')).toContainText('55%');
  await page.getByRole('button', { name: 'Fit width' }).click();
  await expect(page.locator('.pdf-zoom-controls')).toContainText('100%');
  await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await captureViewport(page, 'documents-round5-airead-desktop-1440-populated-real', 1440, 900);

  const pageThreeText =
    'Unique page three clause: Sapphire Pavilion shall host the special procedural conference on the third calendar day.';
  await page.locator('.document-page-text-list summary').click();
  await page.locator('.document-page-text-list .document-page-citation').getByText('Page 3').click();
  await expect(page).toHaveURL(/page=3/);
  await expect(page.getByLabel('Jump to page')).toHaveValue('3', { timeout: 60000 });
  await expect(page.getByLabel('PDF page 3')).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel('PDF page 3')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  await expect(page.locator('#page-3')).toContainText(pageThreeText);
  await expect(page.locator('.pdf-page-card[data-page-card="3"] .pdf-text-layer')).toContainText(
    /Unique page three clause/,
  );
  await expectPageRatio(page, 3);
  const citationToolbarBounds = await page.locator('.pdf-toolbar').boundingBox();
  const citationLabelBounds = await page
    .locator('.pdf-page-card[data-page-card="3"] .pdf-page-label')
    .boundingBox();
  expect(citationToolbarBounds).not.toBeNull();
  expect(citationLabelBounds).not.toBeNull();
  const citationOffset = citationLabelBounds!.y - citationToolbarBounds!.y - citationToolbarBounds!.height;
  expect(citationOffset).toBeGreaterThanOrEqual(0);
  expect(citationOffset).toBeLessThanOrEqual(150);
  await page.evaluate(() => window.scrollTo(0, 0));
  await captureViewport(page, 'documents-round5-citation-page3-desktop-1440-real', 1440, 900);

  expect(document.content_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(document.page_count).toBe(5);
});

test('upload control reports completion and opens the uploaded PDF with a source-linked field', async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await signIn(request);
  await openWithToken(page, token, '/documents');
  const fileName = 'arbitration-text-layer.pdf';
  await page.locator('input[type="file"]').setInputFiles('tests/fixtures/arbitration-text-layer.pdf');
  const uploadProgress = page.getByRole('progressbar', { name: `${fileName} upload progress` });
  await expect(uploadProgress).toHaveAttribute('value', '100', { timeout: 30000 });
  const uploadedLink = page.getByRole('link', { name: fileName, exact: true });
  await expect(uploadedLink).toBeVisible({ timeout: 30000 });
  const uploadedHref = await uploadedLink.getAttribute('href');
  expect(uploadedHref).toBeTruthy();
  const uploadedUrl = new URL(uploadedHref!, process.env.TANTARA_WEB_URL ?? 'http://127.0.0.1:3010');
  const uploadedId = uploadedUrl.pathname.split('/').at(-1)!;
  const headers = { Authorization: `Bearer ${token}` };
  await expect
    .poll(async () =>
      request
        .get(`${apiUrl}/documents/${uploadedId}/job`, { headers })
        .then((response) => response.json())
        .then((job) => job.status),
    )
    .toBe('ready');
  const extractionResponse = await request.post(`${apiUrl}/documents/${uploadedId}/ai-read`, {
    headers,
    data: {},
  });
  expect(extractionResponse.ok()).toBeTruthy();
  await uploadedLink.click();
  await expect(page.getByLabel('PDF page 1')).toBeVisible({ timeout: 60000 });
  await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  const clause = page.locator('.ai-read-field[data-field-key="arbitration_clause"]');
  await expect(clause).toBeVisible({ timeout: 90000 });
  await expect(clause.locator('.ai-source-page')).toHaveText('Page 1');
  await expect(page.getByLabel('PDF page 1')).toBeVisible();
  await captureViewport(page, 'documents-round5-upload-outcome-desktop-1440-real', 1440, 900);
  let deleteSucceeded = false;
  for (let attempt = 0; attempt < 3 && !deleteSucceeded; attempt += 1) {
    try {
      const deleteResponse = await request.delete(`${apiUrl}/documents/${uploadedId}`, { headers });
      deleteSucceeded = deleteResponse.ok();
    } catch {
      deleteSucceeded = false;
    }
    if (!deleteSucceeded) await page.waitForTimeout(500);
  }
  expect(deleteSucceeded).toBeTruthy();
});

test('library filters, layout, selection, preview, and PDF download change state', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const documents = await request
    .get(`${apiUrl}/documents?page_size=100`, { headers })
    .then((response) => response.json());
  const firstDocument = documents.items.find(
    (item: { id: string; title: string; status: string; filename: string }) =>
      item.filename === 'page-three-motion.pdf' && item.status === 'ready',
  ) as { id: string; title: string; status: string; filename: string } | undefined;
  if (!firstDocument) throw new Error('Seeded page-three-motion.pdf is not present in the real API list.');
  await openWithToken(page, token, '/documents');
  await expect(page.locator('.documents-table tbody tr').first()).toBeVisible({ timeout: 60000 });

  await page.getByLabel('Filter by status').selectOption('ready');
  const readyCount = documents.items.filter((item: { status: string }) => item.status === 'ready').length;
  await expect(page.locator('.documents-table tbody tr')).toHaveCount(readyCount);
  await page.getByRole('button', { name: 'Grid view' }).click();
  await expect(page.locator('.documents-list.grid .document-card').first()).toBeVisible();
  await expect(page.locator('.documents-list.grid .document-card')).toHaveCount(readyCount);
  await page.getByRole('button', { name: 'List view' }).click();
  const titleLink = page.getByRole('link', { name: firstDocument.title, exact: true }).first();
  const selectedCheckbox = page.getByRole('checkbox', { name: `Select ${firstDocument.title}` }).first();
  await selectedCheckbox.check();
  await expect(page.getByText('1 selected')).toBeVisible();
  await selectedCheckbox.uncheck();
  await expect(page.getByText('1 selected')).toHaveCount(0);
  const firstRow = page.locator('.documents-table tbody tr').filter({ has: titleLink }).first();
  await firstRow.locator('td').nth(1).click();
  await expect(firstRow).toHaveClass(/previewed/);
  const previewCanvas = page.locator('.document-preview-pane canvas').first();
  await expect(previewCanvas).toHaveAttribute('data-rendered', 'true', { timeout: 60000 });
  await page.getByRole('link', { name: `Open ${firstDocument.title}` }).click();
  await expect(page).toHaveURL(new RegExp(`/documents/${firstDocument.id}$`));
  await expect(page.getByLabel('PDF page 1')).toHaveAttribute('data-rendered', 'true', {
    timeout: 60000,
  });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  const downloadedFile = await downloadPromise;
  expect(downloadedFile.suggestedFilename()).toMatch(/\.pdf$/i);
  expect(await downloadedFile.path()).toBeTruthy();
  await captureViewport(page, 'documents-round5-download-viewer-desktop-1440-real', 1440, 900);
});
