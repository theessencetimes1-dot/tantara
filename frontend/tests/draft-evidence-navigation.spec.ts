import { expect, test, type APIRequestContext } from '@playwright/test';

const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const apiV1 = `${apiOrigin}/api/v1`;

async function signIn(request: APIRequestContext) {
  const response = await request.post(`${apiV1}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}

test('evidence links navigate from the editable draft and preserve editing', async ({ page, request }) => {
  const token = await signIn(request);
  const headers = { Authorization: `Bearer ${token}` };
  const casesResponse = await request.get(`${apiV1}/cases?page=1&page_size=100`, { headers });
  expect(casesResponse.ok()).toBeTruthy();
  const cases = (await casesResponse.json()).items as Array<{ id: string; title: string }>;
  const selectedCase = cases.find((item) => item.title === 'ABC Pvt. Ltd. vs. XYZ Ltd.');
  expect(selectedCase, 'the authenticated demo case is available').toBeTruthy();

  const search = new URLSearchParams({
    query: 'arbitration agreement',
    case_ids: selectedCase!.id,
    page_size: '100',
  });
  const searchResponse = await request.get(`${apiV1}/search/documents?${search}`, { headers });
  expect(searchResponse.ok()).toBeTruthy();
  const hits = (await searchResponse.json()).items as Array<{
    chunk_id: string;
    document_id: string;
    document_title: string;
    page_number: number;
    snippet: string;
  }>;
  const source = hits.find((hit) => hit.page_number > 0);
  expect(source, 'real indexed case evidence is available').toBeTruthy();

  const content = [
    '# Statement of Claim',
    '',
    '## Evidence',
    '',
    `- [${source!.chunk_id}] ${source!.document_title}, page ${source!.page_number}: ${source!.snippet}`,
    '',
    'This saved draft cites evidence from the selected case record for counsel review.',
  ].join('\n');
  const draftResponse = await request.post(`${apiV1}/drafts`, {
    headers,
    data: {
      title: 'Citation navigation review draft',
      document_type: 'Statement of Claim',
      case_id: selectedCase!.id,
      content_markdown: content,
    },
  });
  expect(draftResponse.status(), await draftResponse.text()).toBe(200);
  const draft = (await draftResponse.json()) as { id: string };

  try {
    const savedDraft = await request.get(`${apiV1}/drafts/${draft.id}`, { headers });
    expect(savedDraft.status()).toBe(200);
    expect((await savedDraft.json()).content_markdown).toBe(content);

    await page.addInitScript((value) => localStorage.setItem('tantara_token', value), token);
    await page.goto(`/drafts?id=${draft.id}`);
    const editor = page.locator('.draft-editor');
    await expect(editor).toBeVisible();
    const citation = editor.locator('a.draft-evidence-link[href*="?page="]').first();
    await expect(citation).toBeVisible();
    const href = await citation.getAttribute('href');
    expect(href).toBe(`/documents/${source!.document_id}?page=${source!.page_number}`);

    await citation.click();
    await expect(page).toHaveURL(
      new RegExp(`/documents/${source!.document_id}\\?page=${source!.page_number}$`),
    );
    await expect(page.locator(`.pdf-page-card[data-page-card="${source!.page_number}"]`)).toBeVisible();

    await page.goto(`/drafts?id=${draft.id}`);
    await expect(editor).toBeVisible();
    const editPhrase = 'EDITED AFTER CITATION NAVIGATION';
    await editor.click();
    await page.keyboard.press('ControlOrMeta+End');
    await page.keyboard.press('Enter');
    await page.keyboard.insertText(editPhrase);
    await expect(editor).toContainText(editPhrase);

    const saveResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/v1/drafts/${draft.id}/versions` &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save version' }).click();
    expect((await saveResponse).status()).toBe(200);
    const persisted = await request.get(`${apiV1}/drafts/${draft.id}`, { headers });
    expect((await persisted.json()).content_markdown).toContain(editPhrase);
  } finally {
    const deleted = await request.delete(`${apiV1}/drafts/${draft.id}`, { headers });
    expect(deleted.ok()).toBeTruthy();
  }
});
