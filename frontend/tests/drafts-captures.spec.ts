import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test';

const apiOrigin = (process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010').replace(/\/$/, '');
const apiV1 = `${apiOrigin}/api/v1`;
const shots = 'docs/screenshots';
const desktop = { width: 1440, height: 900 };
const mobile = { width: 390, height: 844 };
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

async function login(api: APIRequestContext) {
  const response = await api.post(`${apiV1}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}
async function settle(page: Page) {
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  await expect(page.locator('.skeleton, [class*="skeleton"]')).toHaveCount(0);
}
async function capture(page: Page, name: string, viewport: typeof desktop | typeof mobile) {
  await (await import('node:fs/promises')).mkdir(shots, { recursive: true });
  await page.setViewportSize(viewport);
  if (viewport.width === 390) {
    await page.waitForTimeout(250); // allow the sidebar's CSS close transition to finish before measuring it
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, 'mobile document must not overflow horizontally').toBeLessThanOrEqual(390);
    const sidebar = page.locator('.sidebar');
    const heading = page.locator('main h1').first();
    const targets = [heading, page.locator('.draft-editor').first(), page.locator('#case').first()];
    const side = await sidebar.boundingBox();
    if (side)
      for (const target of targets) {
        if (!(await target.count()) || !(await target.isVisible())) continue;
        const box = await target.boundingBox();
        if (box)
          expect(
            side.x + side.width <= box.x ||
              box.x + box.width <= side.x ||
              side.y + side.height <= box.y ||
              box.y + box.height <= side.y,
            `closed sidebar ${JSON.stringify(side)} must not intersect ${JSON.stringify(box)}`,
          ).toBeTruthy();
      }
  }
  await settle(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}
async function docxText(bytes: Buffer) {
  const { inflateRawSync } = await import('node:zlib');
  for (let offset = 0; offset + 30 < bytes.length;) {
    if (bytes.readUInt32LE(offset) !== 0x04034b50) break;
    const method = bytes.readUInt16LE(offset + 8),
      size = bytes.readUInt32LE(offset + 18),
      nameLength = bytes.readUInt16LE(offset + 26),
      extraLength = bytes.readUInt16LE(offset + 28);
    const name = bytes.subarray(offset + 30, offset + 30 + nameLength).toString();
    const start = offset + 30 + nameLength + extraLength,
      end = start + size;
    if (name === 'word/document.xml')
      return (
        method === 8 ? inflateRawSync(bytes.subarray(start, end)) : bytes.subarray(start, end)
      ).toString('utf8');
    offset = end;
  }
  throw new Error('DOCX archive is missing word/document.xml');
}
function ascii85Decode(input: string) {
  const source = input.replace(/\s|~>/g, '');
  const out: number[] = [];
  for (let i = 0; i < source.length;) {
    if (source[i] === 'z') {
      out.push(0, 0, 0, 0);
      i++;
      continue;
    }
    const part = source.slice(i, i + 5);
    i += part.length;
    if (part.length < 2) break;
    const count = part.length;
    let value = 0;
    const padded = part.padEnd(5, 'u');
    for (const ch of padded) value = value * 85 + (ch.charCodeAt(0) - 33);
    const bytes = Buffer.alloc(4);
    bytes.writeUInt32BE(value >>> 0);
    out.push(...bytes.subarray(0, count - 1));
  }
  return Buffer.from(out);
}

test('captures live seeded drafts and autofill states at desktop and mobile sizes', async ({ page }) => {
  test.setTimeout(420_000);
  const api = await request.newContext();
  expect(new URL(apiOrigin).port, 'capture suite targets the integration backend').toBe('8010');
  expect(new URL(apiOrigin).port, 'capture test uses the integration API port').toBe('8010');
  const token = await login(api);
  const headers = { Authorization: `Bearer ${token}` };
  await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
  const casesResponse = await api.get(`${apiV1}/cases?page=1&page_size=100`, { headers });
  expect(casesResponse.status()).toBe(200);
  const cases = (await casesResponse.json()).items as Array<Record<string, any>>;
  const selectedCase = cases.find((c) => c.title === 'ABC Pvt. Ltd. vs. XYZ Ltd.');
  if (!selectedCase)
    throw new Error('Seeded case ABC Pvt. Ltd. vs. XYZ Ltd. is required for real-backend captures.');
  const caseReference = String(selectedCase.reference_number);
  const templatesResponse = await api.get(`${apiV1}/draft-templates`, { headers });
  expect(templatesResponse.status()).toBe(200);
  const template = (await templatesResponse.json()).items[0];
  const initialDraftList = await api.get(`${apiV1}/drafts?page=1&page_size=100`, { headers });
  let existingDrafts = (await initialDraftList.json()).items as Array<Record<string, any>>;
  for (let i = existingDrafts.length; i < 21; i++) {
    const create = await api.post(`${apiV1}/drafts`, {
      headers,
      data: {
        title: `Mobile list review ${i + 1}`,
        document_type: 'Statement of Claim',
        case_id: selectedCase.id,
        content_markdown: '[REVIEW: Confirm the facts before filing.]',
      },
    });
    expect(create.status()).toBe(200);
  }
  const boundList = await api.get(`${apiV1}/drafts?page=1&page_size=100`, { headers });
  existingDrafts = (await boundList.json()).items;
  expect(existingDrafts.length).toBeGreaterThanOrEqual(21);
  const aiSettingsResponse = await api.get(`${apiV1}/settings/ai`, { headers });
  const originalAI = await aiSettingsResponse.json();

  await page.setViewportSize(desktop);
  await page.goto('/drafts');
  await expect(page.getByRole('heading', { name: 'AI Case Drafts' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('tantara_token'))).toBe(token);
  await expect(page.getByRole('link', { name: 'Start a draft' })).toBeVisible();
  await capture(page, 'drafts-list-desktop-1440', desktop);
  await capture(page, 'drafts-list-mobile-390', mobile);
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.locator('.sidebar')).toHaveClass(/open/);
  await expect
    .poll(async () => (await page.locator('.sidebar').boundingBox())?.x ?? -1)
    .toBeGreaterThanOrEqual(0);
  const draftsNavLink = page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'AI Drafts' });
  const navBox = await draftsNavLink.boundingBox();
  expect(navBox && navBox.x).toBeGreaterThanOrEqual(0);
  expect(navBox && navBox.x + navBox.width).toBeLessThanOrEqual(390);
  expect(navBox && navBox.y + navBox.height).toBeLessThanOrEqual(844);
  await draftsNavLink.click();
  await expect(page.locator('.sidebar')).not.toHaveClass(/open/);
  const headingBox = await page.getByRole('heading', { name: 'AI Case Drafts' }).boundingBox();
  const sidebarBox = await page.locator('.sidebar').boundingBox();
  if (headingBox && sidebarBox)
    expect(
      sidebarBox.x + sidebarBox.width <= headingBox.x ||
        headingBox.x + headingBox.width <= sidebarBox.x ||
        sidebarBox.y + sidebarBox.height <= headingBox.y ||
        headingBox.y + headingBox.height <= sidebarBox.y,
    ).toBeTruthy();
  const startBox = await page.getByRole('link', { name: 'Start a draft' }).boundingBox();
  expect(startBox && startBox.y + startBox.height).toBeLessThanOrEqual(844);
  const firstRow = page.locator('.draft-recent-list .draft-version').first();
  await expect(page.locator('.draft-recent-list .draft-version')).toHaveCount(21);
  await expect(firstRow.locator('strong')).toBeVisible();
  await expect(firstRow.locator('small')).toBeVisible();
  await expect(firstRow.locator('time')).toBeVisible();
  await expect(firstRow.getByRole('link', { name: 'Open' })).toBeVisible();
  await page.setViewportSize(desktop);

  await page.locator('#case').selectOption(String(selectedCase.id));
  const source = page.locator('.draft-source input').first();
  await expect.poll(() => page.locator('.draft-source input').count()).toBeGreaterThan(0);
  await page.getByText(/Choose from \d+ case documents/).click();
  await expect(source).toBeVisible();
  await source.check();
  await expect(page.locator('#case')).toHaveValue(String(selectedCase.id));
  const generationResponsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/api/v1/drafts/generate' &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Generate Draft' }).click();
  const generationResponse = await generationResponsePromise;
  expect(generationResponse.status(), await generationResponse.text()).toBe(200);
  const generated = await generationResponse.json();
  await expect(page.locator('.draft-case-reference')).toBeVisible({ timeout: 180_000 });
  await expect(page.locator('.draft-case-reference')).toContainText(caseReference);
  const draftUrl = new URL(page.url());
  let draftId = draftUrl.searchParams.get('id');
  expect(draftId).toBeTruthy();
  const persisted = await api.get(`${apiV1}/drafts/${draftId}`, { headers });
  expect(persisted.status()).toBe(200);
  expect((await persisted.json()).content_markdown).toBe(generated.content_markdown);
  expect(String(generated.generation_kind)).toBeTruthy();
  if (generated.model?.model)
    await expect(page.locator('.draft-generation-meta')).toContainText(generated.model.model);
  await expect(page.locator('.draft-generation-meta')).toContainText(generated.generation_kind);
  expect(generated.content_markdown).toContain(selectedCase.title);
  expect(generated.content_markdown).toContain(selectedCase.claimant);
  expect(generated.content_markdown).toContain(selectedCase.respondent);
  for (const line of generated.content_markdown.split('\n').filter((x: string) => /^Claimant:/i.test(x)))
    expect(line).toContain(selectedCase.claimant);
  for (const line of generated.content_markdown.split('\n').filter((x: string) => /^Respondent:/i.test(x)))
    expect(line).toContain(selectedCase.respondent);
  const generatedPageLink = page.locator('.draft-page-chips a[href*="?page="]').first();
  if (await generatedPageLink.count()) {
    const href = await generatedPageLink.getAttribute('href');
    expect(href).toBeTruthy();
    page.on('pageerror', (error) => console.log(`citation page error: ${error.stack ?? error.message}`));
    page.on('response', (response) => {
      if (response.status() >= 400) console.log(`citation response ${response.status()} ${response.url()}`);
    });
    const destination = new URL(href!, 'http://localhost');
    const pageNumber = destination.searchParams.get('page')!;
    await generatedPageLink.click();
    await expect(page).toHaveURL(
      new RegExp(`/documents/${destination.pathname.split('/').at(-1)}\\?page=${pageNumber}`),
    );
    const destinationPage = page.locator(`.pdf-page-card[data-page-card="${pageNumber}"]`);
    await expect(destinationPage).toBeVisible();
    await expect(destinationPage).toContainText(`Page ${pageNumber}`);
    await page.goto(`/drafts?id=${draftId}`);
  }
  await expect(page.locator('.draft-editor, .draft-unrecognized')).toBeVisible({ timeout: 60000 });
  let editor = page.locator('.draft-editor');
  const generatedEditorWasRendered = (await editor.count()) > 0;
  if (generatedEditorWasRendered) expect(await editor.innerText()).not.toMatch(/We need to draft a/i);
  let draftIdForEditor = draftId!;
  if (!(await editor.count())) {
    await expect(editor).toHaveCount(0);
    await expect(
      page.getByRole('heading', { name: 'Generated text needs editing — structure not recognised' }),
    ).toBeVisible();
    await expect(page.locator('.draft-unrecognized pre')).toBeHidden();
    await expect(page.locator('.draft-unrecognized')).toContainText('Retry');
    await capture(page, 'draft-review-needed-desktop-1440', desktop);
    await capture(page, 'draft-review-needed-mobile-390', mobile);
    await page.locator('.draft-unrecognized summary').click();
    await expect(page.locator('.draft-unrecognized pre')).toContainText(
      String(generated.content_markdown).slice(0, 30),
    );

    // Use an explicitly case-sourced human review draft for editor/save/export controls.
    const editableBody = `# Statement of Claim\n\n## Parties\nClaimant: ${selectedCase.claimant}\nRespondent: ${selectedCase.respondent}\n\n## Arbitration Agreement\nThe case record identifies ${selectedCase.forum ?? 'the selected institution'} and reference ${caseReference}.\n\n## Relief Sought\n[REVIEW: Relief requested is not available in the supplied case record.]`;
    const editable = await api.post(`${apiV1}/drafts`, {
      headers,
      data: {
        title: 'Statement of Claim (case sourced review)',
        document_type: 'Statement of Claim',
        case_id: selectedCase.id,
        content_markdown: editableBody,
      },
    });
    expect(editable.status()).toBe(200);
    draftIdForEditor = (await editable.json()).id;
    await page.goto(`/drafts?id=${draftIdForEditor}`);
    editor = page.locator('.draft-editor');
    await expect(editor).toBeVisible();
  }
  expect(await editor.innerText()).not.toMatch(UUID);
  expect(await editor.innerText()).not.toMatch(/We need to draft a/i);
  await expect(page.locator('.draft-review-summary')).toBeVisible();
  if (await editor.locator('[data-chunk-id]').count())
    await expect(editor.locator('[data-chunk-id]').first()).toHaveAttribute('data-chunk-id', UUID);
  await capture(page, 'draft-editor-desktop-1440', desktop);
  await capture(page, 'draft-editor-mobile-390', mobile);
  if ((await page.locator('.draft-unrecognized').count()) === 0) {
    await capture(page, 'draft-review-needed-desktop-1440', desktop);
    await capture(page, 'draft-review-needed-mobile-390', mobile);
  }
  draftId = draftIdForEditor;
  const preexistingVersions = (
    await (await api.get(`${apiV1}/drafts/${draftId}/versions`, { headers })).json()
  ).items as Array<Record<string, any>>;
  if (!preexistingVersions.length) {
    const currentDraft = await (await api.get(`${apiV1}/drafts/${draftId}`, { headers })).json();
    const firstSnapshot = await api.post(`${apiV1}/drafts/${draftId}/versions`, {
      headers,
      data: { content_markdown: currentDraft.content_markdown, change_note: 'Initial saved snapshot' },
    });
    expect(firstSnapshot.status()).toBe(200);
  }
  const beforeEdit = await api.get(`${apiV1}/drafts/${draftId}/versions`, { headers });
  const initialVersions = (await beforeEdit.json()).items as Array<Record<string, any>>;
  const generatedVersionId = initialVersions[0]?.id;
  const originalEditorContent = (await (await api.get(`${apiV1}/drafts/${draftId}`, { headers })).json())
    .content_markdown as string;
  const uniquePhrase = 'COUNSEL REVIEW PHRASE LUNA 2026';
  let savedRequestUrl = '';
  let savedVersionResponse: Record<string, any> | undefined;
  editor = page.locator('.draft-editor');
  await expect(editor, `draft editor should be ready at ${page.url()}`).toBeVisible({ timeout: 60_000 });
  await page.getByRole('tab', { name: 'Draft', exact: true }).click();
  await expect(editor).toBeVisible();
  await editor.click();
  await page.keyboard.press('ControlOrMeta+End');
  await page.keyboard.press('Enter');
  await page.keyboard.insertText(uniquePhrase);
  const saveVersion = page.getByRole('button', { name: 'Save version' });
  await expect(saveVersion).toBeVisible();
  await expect(editor).toContainText(uniquePhrase);
  const saveRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === `/api/v1/drafts/${draftId}/versions` && request.method() === 'POST',
  );
  const saveResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/v1/drafts/${draftId}/versions` &&
      response.request().method() === 'POST',
  );
  await saveVersion.click();
  const savedRequest = await saveRequest;
  savedRequestUrl = savedRequest.url();
  expect(savedRequest.postDataJSON().content_markdown).toContain(uniquePhrase);
  const savedResponse = await saveResponse;
  const responseText = await savedResponse.text();
  expect(savedResponse.status(), responseText).toBe(200);
  savedVersionResponse = JSON.parse(responseText);
  await expect(page.getByRole('status')).toContainText(/saved/i);
  await page.reload();
  await expect(editor, `draft editor should reload at ${page.url()}`).toBeVisible({ timeout: 60_000 });
  await expect(editor).toContainText(uniquePhrase);
  const reloaded = await api.get(`${apiV1}/drafts/${draftId}`, { headers });
  const reloadedDraft = await reloaded.json();
  expect(
    reloadedDraft.content_markdown,
    `draft ${draftId} after save; API ${new URL(apiOrigin).origin}; request ${savedRequestUrl}; version ${JSON.stringify(savedVersionResponse)}`,
  ).toContain(uniquePhrase);
  const savedVersions = (await (await api.get(`${apiV1}/drafts/${draftId}/versions`, { headers })).json())
    .items as Array<Record<string, any>>;
  expect(savedVersions.length).toBeGreaterThan(initialVersions.length);
  expect(savedVersions.length).toBeGreaterThanOrEqual(2);
  expect(savedVersionResponse?.version_number).toEqual(savedVersions[0]?.version_number);
  expect(savedVersions[0]?.id).toBe(savedVersionResponse?.id);
  if (generatedVersionId) expect(savedVersions.some((v) => v.id === generatedVersionId)).toBeTruthy();
  await page.getByRole('tab', { name: 'History', exact: true }).click();
  await expect(page.locator('.draft-version-row').first()).toContainText('Current');
  await expect(page.locator('.draft-version-row').first().locator('time span')).toHaveCount(2);
  expect(await page.locator('.draft-version-row').first().locator('strong').innerText()).toMatch(
    /^(Version \d+|Snapshot · .+)$/,
  );
  for (const viewport of [desktop, mobile]) {
    await page.setViewportSize(viewport);
    const row = page.locator('.draft-version-row').first();
    const card = page.locator('.draft-history-panel');
    const box = await card.boundingBox();
    for (const descendant of await row.locator('*').all()) {
      const child = await descendant.boundingBox();
      if (child && box) {
        expect(child.x).toBeGreaterThanOrEqual(box.x - 1);
        expect(child.x + child.width).toBeLessThanOrEqual(box.x + box.width + 1);
      }
    }
  }
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Restore' }).last().click();
  await expect(page.getByRole('status')).toContainText(/restored/i, { timeout: 20_000 });
  const restoredTitle = String(initialVersions[0]?.content_markdown ?? originalEditorContent)
    .split('\n')[0]
    .replace(/^#+\s*/, '')
    .slice(0, 20);
  await page.getByRole('tab', { name: 'Draft', exact: true }).click();
  if (await page.locator('.draft-editor').count())
    await expect(page.locator('.draft-editor')).toContainText(restoredTitle);
  await page.getByRole('tab', { name: 'History', exact: true }).click();
  await capture(page, 'draft-version-history-desktop-1440', desktop);
  await capture(page, 'draft-version-history-mobile-390', mobile);
  await page.getByRole('tab', { name: 'Draft', exact: true }).click();

  if (await editor.count()) {
    await editor.click();
    await page.keyboard.press('ControlOrMeta+End');
    await page.keyboard.press('Enter');
    await page.keyboard.insertText(uniquePhrase);
    await page.getByRole('button', { name: 'Save version' }).click();
    await expect(page.getByRole('status')).toContainText(/saved/i);
  }

  for (const format of ['docx', 'pdf'] as const) {
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: `Export ${format.toUpperCase()}` }).click();
    const download = await downloadPromise;
    const path = await download.path();
    expect(path).toBeTruthy();
    const fs = await import('node:fs/promises');
    const bytes = await fs.readFile(path!);
    expect(bytes.byteLength).toBeGreaterThan(200);
    expect(format === 'docx' ? bytes.subarray(0, 4).toString() : bytes.subarray(0, 4).toString()).toBe(
      format === 'docx' ? 'PK\x03\x04' : '%PDF',
    );
    if (format === 'docx') {
      const xml = await docxText(bytes);
      expect(xml).toContain('[REVIEW:');
      expect(xml).toContain(uniquePhrase);
    } else {
      const { inflateSync } = await import('node:zlib');
      const raw = bytes.toString('latin1');
      const streams = [...raw.matchAll(/stream\r?\n([\s\S]*?)\r?\n?endstream/g)]
        .map((match) => {
          try {
            return inflateSync(ascii85Decode(match[1])).toString('latin1');
          } catch {
            return match[1];
          }
        })
        .join('\n');
      expect(`${raw}\n${streams}`).toContain('[REVIEW:');
      expect(`${raw}\n${streams}`).toContain(uniquePhrase);
    }
  }

  await page.goto('/autofill');
  await page.locator('#autofill-case').selectOption(String(selectedCase.id));
  await expect(page.locator('.auto-field').first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Preview fields' }).click();
  await expect(page.getByRole('status')).toContainText(/Preview loaded/i);
  await expect(page.locator('.auto-provenance').first()).toBeVisible();
  const sourcedField = page
    .locator('.auto-field')
    .filter({ has: page.locator('.auto-source-link') })
    .first();
  const sourcedProvenance = await sourcedField.locator('.auto-provenance').innerText();
  const sourcedLabel = await sourcedField.locator('label').innerText();
  if (await sourcedField.locator('.auto-full-value').count()) {
    await sourcedField.locator('.auto-full-value summary').click();
    await expect(sourcedField.locator('.auto-full-value p')).toBeVisible();
  }
  const rejectedField = page.locator('.auto-field').nth(1);
  const rejectedLabel = await rejectedField.locator('label').innerText();
  await rejectedField.getByRole('button', { name: 'Reject', exact: true }).click();
  await expect(rejectedField).toHaveAttribute('aria-label', new RegExp(`${rejectedLabel} Rejected`));
  await sourcedField.getByRole('button', { name: 'Accept', exact: true }).click();
  await expect(sourcedField).toHaveAttribute('aria-label', new RegExp(`${sourcedLabel} Accepted`));
  await expect(page.getByRole('button', { name: /Apply to Draft \(1 accepted\)/ })).toBeVisible();
  await capture(page, 'autofill-preview-desktop-1440', desktop);
  await capture(page, 'autofill-preview-mobile-390', mobile);
  if (await page.locator('.auto-sources .auto-source').count())
    await expect(page.locator('.auto-sources .auto-source').first()).toBeHidden();
  await page.evaluate(() => window.scrollTo(0, 0));
  const applyBox = await page.getByRole('button', { name: /Apply to Draft/ }).boundingBox();
  expect(applyBox && applyBox.y + applyBox.height).toBeLessThanOrEqual(844);
  await page.setViewportSize(desktop);
  await expect
    .poll(() => page.locator('#autofill-draft option').count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  await page.locator('#autofill-draft').selectOption(String(draftId));
  const accepted = await sourcedField.locator('input').inputValue();
  await page.getByRole('button', { name: /Apply to Draft/ }).click();
  await expect(page.locator('.auto-message[role="status"]')).toContainText(/Applied/i);
  await expect(sourcedField).toHaveAttribute('aria-label', new RegExp(`${sourcedLabel} Accepted`));
  await expect(page.getByRole('button', { name: /Apply to Draft \(1 accepted\)/ })).toBeDisabled();
  const afterApply = (await (await api.get(`${apiV1}/drafts/${draftId}`, { headers })).json())
    .content_markdown as string;
  expect(afterApply).toContain(accepted);
  const expectedProvenance = sourcedProvenance.includes('Extracted') ? 'extracted_reviewed' : 'verified';
  expect(afterApply).toContain(`- ${sourcedLabel}: ${accepted} (provenance: ${expectedProvenance})`);
  expect(afterApply).toContain('source:');
  await capture(page, 'autofill-applied-desktop-1440', desktop);
  await capture(page, 'autofill-applied-mobile-390', mobile);
  await page.reload();
  await page.locator('#autofill-case').selectOption(String(selectedCase.id));
  await expect
    .poll(() => page.locator('#autofill-draft option').count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  await page.locator('#autofill-draft').selectOption(String(draftId));
  expect(
    (await (await api.get(`${apiV1}/drafts/${draftId}`, { headers })).json()).content_markdown,
  ).toContain(accepted);

  await api.patch(`${apiV1}/settings/ai`, {
    headers,
    data: {
      base_url: 'http://127.0.0.1:8999/v1',
      model: originalAI.model,
      top_k: originalAI.top_k,
      temperature: originalAI.temperature,
    },
  });
  await page.goto('/drafts');
  await page.locator('#case').selectOption(String(selectedCase.id));
  await page.getByRole('button', { name: 'Generate Draft' }).click();
  await expect(page.getByRole('status')).toContainText(/local model is unavailable/i, { timeout: 60_000 });
  const unavailableId = new URL(page.url()).searchParams.get('id');
  expect(unavailableId).toBeTruthy();
  const draftsBeforeRetry = (
    await (await api.get(`${apiV1}/drafts?page=1&page_size=100`, { headers })).json()
  ).total;
  await capture(page, 'draft-model-unavailable-desktop-1440', desktop);
  await capture(page, 'draft-model-unavailable-mobile-390', mobile);
  await page.getByRole('button', { name: 'Retry generation' }).click();
  await expect(page.getByRole('status')).toContainText(/local model is unavailable/i, { timeout: 60_000 });
  expect(new URL(page.url()).searchParams.get('id')).not.toBe(unavailableId);
  const draftsAfterRetry = (await (await api.get(`${apiV1}/drafts?page=1&page_size=100`, { headers })).json())
    .total;
  expect(draftsAfterRetry).toBeGreaterThan(draftsBeforeRetry);
  await api.patch(`${apiV1}/settings/ai`, {
    headers,
    data: {
      base_url: originalAI.base_url,
      model: originalAI.model,
      top_k: originalAI.top_k,
      temperature: originalAI.temperature,
    },
  });
  await api.dispose();
});
