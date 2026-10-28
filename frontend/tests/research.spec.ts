import { expect, test, type Page } from '@playwright/test';
import { documentPageUrl } from '../src/features/research/document-url';
import { normalizeResearchAnswer, type ResearchSource } from '../src/features/research/api';
import { normalizeStrategyData } from '../src/features/strategy/api';
import { normalizeAskResponse } from '../src/lib/api/endpoints';
import {
  citationAccessibleLabel,
  answerStatusLabel,
  citationLink,
  groupSources,
  normalizeDocumentTitle,
} from '../src/features/research/presentation';

const apiBase = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const apiRoot = `${apiBase}/api/v1`;
const credentials = { email: 'advocate@tantara.local', password: 'tantara-local' };
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page) {
  const response = await page.request.post(`${apiRoot}/auth/login`, { data: credentials });
  expect(response.ok(), `Login failed: ${await response.text()}`).toBeTruthy();
  const token = (await response.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
}

async function authHeader(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('tantara_token'));
  return { Authorization: `Bearer ${token}` };
}

async function waitSettled(page: Page) {
  await expect(page.getByRole('heading', { name: 'Research Desk' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('[aria-busy="true"], .skeleton, [data-loading="true"]')).toHaveCount(0);
}

async function capture(page: Page, name: string, focusSelector?: string) {
  if (focusSelector) {
    const focus = page.locator(focusSelector).last();
    const focusHeading = focus.locator('.turn-label, h1, h2, h3, strong').first();
    if (await focusHeading.count())
      await focusHeading.evaluate((element) => element.scrollIntoView({ block: 'center' }));
    else await focus.evaluate((element) => element.scrollIntoView({ block: 'center' }));
    const box = await focus.boundingBox();
    const visibleHeading = await focusHeading.boundingBox();
    const header = await page.locator('.topbar').boundingBox();
    if (box && header && visibleHeading) {
      expect(visibleHeading.y).toBeGreaterThanOrEqual(header.y + header.height);
      if (box.height <= (await page.evaluate(() => window.innerHeight)) - header.height)
        expect(box.y + box.height).toBeLessThanOrEqual(await page.evaluate(() => window.innerHeight));
    }
  } else await page.evaluate(() => window.scrollTo(0, 0));
  if ((await page.evaluate(() => window.innerWidth)) <= 500) {
    await page.waitForFunction(() => {
      const sidebar = document.querySelector('.sidebar');
      return !sidebar || sidebar.getBoundingClientRect().right <= 0;
    });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const title = page.locator('.research-page h1, main h1').first();
    const titleBox = await title.boundingBox();
    expect(titleBox?.x).toBeGreaterThanOrEqual(0);
    expect((titleBox?.x ?? 0) + (titleBox?.width ?? 0)).toBeLessThanOrEqual(390);
    if (await page.locator('.research-page').count()) {
      const outOfBounds = await page.locator('.research-page').evaluate((root) =>
        Array.from(root.querySelectorAll<HTMLElement>('*'))
          .filter((element) => {
            const style = getComputedStyle(element);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && (rect.left < 0 || rect.right > window.innerWidth);
          })
          .map((element) => `${element.tagName.toLowerCase()}.${element.className.toString()}`),
      );
      expect(outOfBounds).toEqual([]);
    }
  }
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).not.toBeEmpty();
  await expect(page.locator('[aria-busy="true"], .skeleton, [data-loading="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem('tantara_token'))).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({
    path:
      name === 'research-desktop-no-evidence'
        ? '../docs/screenshots/research-no-evidence-1440.png'
        : name === 'research-desktop-scope-selected'
          ? '../docs/screenshots/research-collection-selected-1440.png'
          : `docs/screenshots/${name}.png`,
    fullPage: (await page.evaluate(() => window.innerWidth)) > 500,
  });
}

async function answerQuestion(page: Page, question: string, via: 'button' | 'suggestion' = 'button') {
  let payload: { status: string; [key: string]: unknown } | undefined;
  let action: 'button' | 'suggestion' = via;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/ai/ask') && response.request().method() === 'POST',
      { timeout: 30_000 },
    );
    if (action === 'suggestion') {
      await page.getByRole('button', { name: question, exact: true }).click();
    } else {
      await page.getByRole('textbox', { name: 'Research question' }).fill(question);
      await page.getByRole('button', { name: 'Ask', exact: true }).click();
    }
    const response = await responsePromise;
    expect(response.ok(), `Ask failed: ${await response.text()}`).toBeTruthy();
    payload = await response.json();
    if (payload?.status !== 'embedding_unavailable') break;
    action = 'button';
    await expect(page.getByRole('button', { name: 'Ask', exact: true })).toBeEnabled();
    await page.waitForTimeout(250);
  }
  if (!payload) throw new Error('Research request did not produce a response.');
  return payload as {
    status: string;
    answer?: string;
    citations?: Array<{
      citation_ref?: string;
      citation_number?: number;
      document_id: string;
      document_title: string;
      chunk_id: string;
      page_number: number;
      excerpt: string;
      retrieval_score?: number;
    }>;
    sources?: Array<{
      citation_ref?: string;
      citation_number?: number;
      document_id: string;
      document_title: string;
      chunk_id: string;
      page_number: number;
      excerpt: string;
      retrieval_score?: number;
    }>;
    disclaimer?: string;
    model?: unknown;
    answer_kind?: string;
    generation_kind?: string;
    answer_basis?: string;
    supports?: Array<{ chunk_id: string; document_id: string; page_number: number; quote: string }>;
    context_fields?: Array<{ field: string; value: string; source: string }>;
    conflicts?: Array<{
      field: string;
      case_value: string;
      excerpt_chunk_id: string;
      page_number: number;
    }>;
    insufficient_evidence?: boolean;
    total?: number;
    research_session_id?: string;
    message_id?: string;
  };
}

test('documentPageUrl preserves document, page, and chunk contract', () => {
  expect(documentPageUrl('doc/1', 7, 'chunk 2')).toBe('/documents/doc%2F1?page=7&chunk=chunk+2');
});

test('citation formatter, source grouping, and human status labels stay readable', () => {
  const sources: ResearchSource[] = [
    {
      document_id: 'doc-1',
      document_title: ' Scanned Arbitration\\nAgreement ',
      chunk_id: 'chunk-1',
      page_number: 1,
      excerpt: 'Same quotation.',
      retrieval_score: 0.032786,
    },
    {
      document_id: 'doc-1',
      document_title: 'Scanned Arbitration Agreement',
      chunk_id: 'chunk-2',
      page_number: 2,
      excerpt: 'Same quotation.',
      retrieval_score: 0.03,
    },
  ];
  expect(citationLink(sources[0])).toEqual({
    label: 'Scanned Arbitration Agreement · Page 1',
    href: '/documents/doc-1?page=1&chunk=chunk-1',
    chunkId: 'chunk-1',
  });
  expect(citationAccessibleLabel(sources[0])).toBe('Scanned Arbitration Agreement · Page 1');
  const grouped = groupSources(sources);
  expect(grouped).toHaveLength(1);
  expect(grouped[0].title).toBe('Scanned Arbitration Agreement');
  expect(grouped[0].pages.map((page) => page.page)).toEqual([1, 2]);
  expect(grouped[0].excerptGroups).toHaveLength(1);
  expect(grouped[0].excerptGroups[0].sources).toHaveLength(2);
  expect(normalizeDocumentTitle('Scanned Arbitration\\nAgreement')).toBe('Scanned Arbitration Agreement');
  expect(answerStatusLabel('ok')).toBe('Response returned · provenance unavailable');
  expect(answerStatusLabel('ok', 'model_generated')).toBe('Model response · review sources');
  expect(answerStatusLabel('model_unavailable')).toBe('Evidence only — model unavailable');
  expect(answerStatusLabel('no_evidence')).toBe('No supporting excerpts');
});

test.describe('Research Desk live API controls', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/research');
    await waitSettled(page);
  });

  test.afterEach(async ({ page }) => {
    const headers = await authHeader(page).catch(() => ({}));
    const saved = await page.request.get(`${apiRoot}/ai/saved?page_size=100`, { headers }).catch(() => null);
    if (saved?.ok()) {
      const items = (await saved.json()).items ?? [];
      for (const item of items)
        await page.request.delete(`${apiRoot}/ai/saved/${item.id}`, { headers }).catch(() => null);
    }
    const history = await page.request
      .get(`${apiRoot}/ai/sessions?page_size=100`, { headers })
      .catch(() => null);
    if (history?.ok()) {
      const items = (await history.json()).items ?? [];
      for (const item of items)
        await page.request.delete(`${apiRoot}/ai/sessions/${item.id}`, { headers }).catch(() => null);
    }
  });

  test('shell stays pinned through scroll and navigation; mobile puts the composer first', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/research');
    await waitSettled(page);
    const header = page.locator('.topbar');
    const sidebar = page.locator('.sidebar');
    const content = page.locator('.research-page');
    const initialHeader = await header.boundingBox();
    const initialSidebar = await sidebar.boundingBox();
    const initialContent = await content.boundingBox();
    expect(initialHeader?.y).toBe(0);
    expect(initialSidebar?.y).toBe(0);
    expect(initialSidebar?.height).toBeGreaterThanOrEqual(900);
    expect(initialContent?.y).toBeGreaterThanOrEqual((initialHeader?.height ?? 0) + 10);
    await capture(page, 'research-desktop-empty');
    await page.evaluate(() => window.scrollTo(0, 500));
    expect((await header.boundingBox())?.y).toBe(0);
    expect((await sidebar.boundingBox())?.y).toBe(0);
    await page.goto('/research/documents');
    await expect(page.getByRole('heading', { name: 'Research library' })).toBeVisible();
    expect((await page.locator('.topbar').boundingBox())?.y).toBe(0);
    expect((await page.locator('.sidebar').boundingBox())?.y).toBe(0);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/research');
    await waitSettled(page);
    const composer = page.getByRole('textbox', { name: 'Research question' });
    const composerBox = await composer.boundingBox();
    const historyButton = page.getByRole('button', { name: 'Refresh history' });
    const historyBox = await historyButton.boundingBox();
    expect(composerBox?.y).toBeLessThan(844);
    expect(composerBox?.y).toBeLessThan(historyBox?.y ?? Number.MAX_SAFE_INTEGER);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const h1Box = await page.getByRole('heading', { name: 'Research Desk', exact: true }).boundingBox();
    expect(h1Box?.x).toBeGreaterThanOrEqual(0);
    expect((h1Box?.x ?? 0) + (h1Box?.width ?? 0)).toBeLessThanOrEqual(390);
    const outOfBounds = await page.locator('.research-page').evaluate((root) =>
      Array.from(root.querySelectorAll<HTMLElement>('*'))
        .filter((element) => {
          const style = getComputedStyle(element);
          if (style.display === 'none' || style.visibility === 'hidden') return false;
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && (rect.left < 0 || rect.right > window.innerWidth);
        })
        .map((element) => `${element.tagName.toLowerCase()}.${element.className.toString()}`),
    );
    expect(outOfBounds).toEqual([]);
    const collectionSelect = page.getByLabel('Collection');
    await expect(collectionSelect.getByRole('option', { name: 'Agreements & Contracts' })).toBeAttached();
    await expect(collectionSelect.getByRole('option', { name: 'Awards & Authorities' })).toBeAttached();
    await expect(collectionSelect.getByRole('option', { name: 'Pleadings & Evidence' })).toBeAttached();
    const collectionWidth = await collectionSelect.evaluate(
      (node) => (node as HTMLSelectElement).clientWidth,
    );
    expect(collectionWidth).toBeGreaterThan(200);
    const mobileHeader = page.locator('.topbar');
    const mobileSidebar = page.locator('.sidebar');
    expect((await mobileHeader.boundingBox())?.y).toBe(0);
    for (const element of await mobileHeader.locator(':visible').all()) {
      const box = await element.boundingBox();
      if (!box) continue;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(390);
    }
    const navigationToggle = await page.getByRole('button', { name: 'Open navigation' }).boundingBox();
    expect(navigationToggle?.x).toBeGreaterThanOrEqual(0);
    expect((navigationToggle?.x ?? 0) + (navigationToggle?.width ?? 0)).toBeLessThanOrEqual(390);
    expect((await mobileSidebar.boundingBox())?.y).toBe(0);
    expect((await mobileSidebar.boundingBox())?.height).toBeGreaterThanOrEqual(844);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const mobileNav = page.getByRole('navigation', { name: 'Main navigation' });
    await expect(mobileNav).toBeVisible();
    const mobileDestinations = [
      'Dashboard',
      'My Cases',
      'Clients',
      'Tasks',
      'Calendar',
      'Documents',
      'Search',
      'Research Desk',
      'Drafts & Documents',
      'Smart Autofill',
      'Bundles',
      'Strategy',
      'Community (Arbitration)',
      'Settings',
    ];
    await expect(mobileNav.getByRole('link')).toContainText(mobileDestinations);
    await page.keyboard.press('Escape');
    await capture(page, 'research-mobile-empty');
  });

  test('new research, live scope selectors, refresh, suggestions, Ask, history, saved items, and library work', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'New research' }).click();
    await expect(page.getByRole('textbox', { name: 'Research question' })).toHaveValue('');
    await expect(page.getByRole('heading', { name: 'What are you researching?' })).toBeVisible();
    await expect(page.locator('.turn')).toHaveCount(0);
    await expect(page.locator('.history-item.selected')).toHaveCount(0);
    await expect(page.locator('.source-item')).toHaveCount(0);
    await capture(page, 'research-desktop-new-state');

    const headers = await authHeader(page);
    const documentsResponse = await page.request.get(`${apiRoot}/documents?page_size=100`, { headers });
    expect(documentsResponse.ok()).toBeTruthy();
    const documents = (await documentsResponse.json()).items as Array<{
      id: string;
      case_id?: string;
      jurisdiction?: string;
    }>;
    const scopedDocument = documents.find((document) => document.case_id);
    expect(scopedDocument).toBeTruthy();
    await page.getByLabel('Case filter').selectOption(scopedDocument!.case_id!);
    await page.getByLabel('Jurisdiction').selectOption(scopedDocument!.jurisdiction ?? 'India');
    await expect(page.getByLabel('Case filter')).toHaveValue(scopedDocument!.case_id!);
    await capture(page, 'research-desktop-scope-selected');
    const refreshResponse = page.waitForResponse(
      (response) => response.url().includes('/api/v1/ai/sessions') && response.request().method() === 'GET',
    );
    await page.getByRole('button', { name: 'Refresh history' }).click();
    expect((await refreshResponse).ok()).toBeTruthy();
    await capture(page, 'research-desktop-history-refreshed');

    const suggestedQuestion = 'What is the seat of arbitration?';
    const suggested = await answerQuestion(page, suggestedQuestion, 'suggestion');
    expect(['ok', 'answered']).toContain(suggested.status);
    expect(suggested.answer?.trim().length).toBeGreaterThan(0);
    expect(suggested.citations?.length ?? suggested.sources?.length ?? 0).toBeGreaterThan(0);
    const suggestedSources = suggested.citations ?? suggested.sources ?? [];
    const suggestedDocumentCount = new Set(suggestedSources.map((source) => source.document_id)).size;
    await expect(page.locator('.source-count')).toHaveText(String(suggestedDocumentCount));
    await expect(page.locator('.source-relevance b').first()).toHaveText(/^\d+\.\d{3}$/);
    await expect(page.locator('.history-item').filter({ hasText: suggestedQuestion })).toBeVisible();
    await capture(page, 'research-desktop-suggested-question');

    await page.getByLabel('Case filter').selectOption('');
    await page.getByLabel('Collection').selectOption('');
    await page.getByLabel('Jurisdiction').selectOption('');
    await page.getByRole('button', { name: 'Refresh history' }).click();
    const historyEntry = page.locator('.history-item').first();
    await expect(historyEntry).toBeVisible();
    await historyEntry.click();
    await expect(page.getByText(/\d{2} [A-Z][a-z]{2} \d{4}/).first()).toBeVisible();
    await capture(page, 'research-desktop-history-entry');

    const saveResponse = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/ai/saved') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save', exact: true }).last().click();
    expect((await saveResponse).ok()).toBeTruthy();
    await expect(page.getByRole('button', { name: 'Saved answer' })).toBeVisible();
    await capture(page, 'research-desktop-saved-answer');
    await page.getByRole('button', { name: 'Saved answer' }).click();
    await expect(page.locator('.turn.assistant').last()).toBeVisible();
    await expect(page.locator('.turn.assistant').last().locator('.answer-citation')).toHaveCount(
      suggestedSources.length,
    );
    await expect(page.locator('.source-item')).toHaveCount(
      new Set(suggestedSources.map((source) => source.document_id)).size,
    );
    await capture(page, 'research-desktop-saved-answer-opened');

    await page.locator('a[href="/research/documents"]').click();
    await expect(page).toHaveURL(/\/research\/documents$/);
    await expect(page.getByRole('heading', { name: 'Research library' })).toBeVisible();
    await capture(page, 'research-desktop-library');
    await page.getByRole('link', { name: 'Back to Research Desk' }).click();
    await waitSettled(page);

    await page.getByRole('button', { name: 'New research' }).click();
    await capture(page, 'research-desktop-new-after-history');
    const asked = await answerQuestion(page, 'What is the seat of arbitration?', 'button');
    expect(['ok', 'answered']).toContain(asked.status);
    expect(asked.answer?.trim().length).toBeGreaterThan(0);
    await capture(page, 'research-desktop-ask-button');
    await page.reload();
    await waitSettled(page);
    const answerLead = asked
      .answer!.split(/[\n.]|\[\d+\]/)[0]
      .replace(/[“”]$/, '')
      .trim();
    await expect(page.locator('.turn.assistant').last().locator('.answer-text')).toContainText(
      answerLead.replace(/[,;:\s]+$/, ''),
    );
    const restoredCitations = asked.citations ?? asked.sources ?? [];
    await expect(page.locator('.turn.assistant').last().locator('.answer-citation')).toHaveCount(
      restoredCitations.length,
    );
    for (const source of restoredCitations) {
      const chip = page
        .locator('.turn.assistant')
        .last()
        .getByRole('link', {
          name: `Open ${source.document_title} · Page ${source.page_number}`,
        });
      await expect(chip).toHaveAttribute(
        'href',
        documentPageUrl(source.document_id, source.page_number, source.chunk_id),
      );
    }
    await expect(page.locator('.source-relevance').first()).toContainText('relative to this query');
    await expect(page.locator('.source-item')).toHaveCount(
      new Set(restoredCitations.map((source) => source.document_id)).size,
    );
    await capture(page, 'research-session-restored');
  });

  test('citations show API markers and open the highest cited page', async ({ page }) => {
    const asked = await answerQuestion(page, 'What does the arbitration agreement say about the seat?');
    expect(['ok', 'answered']).toContain(asked.status);
    expect(asked.disclaimer).toBeTruthy();
    const citations = asked.citations ?? asked.sources ?? [];
    expect(citations.length).toBeGreaterThan(0);
    const distinctDocumentIds = new Set(citations.map((citation) => citation.document_id));
    await expect(page.locator('.sources-card header p')).toContainText(
      `${distinctDocumentIds.size} ${distinctDocumentIds.size === 1 ? 'document' : 'documents'}`,
    );
    const displayedExcerpts = await page.locator('.source-excerpt > p').allTextContents();
    expect(new Set(displayedExcerpts).size).toBe(displayedExcerpts.length);
    const answerText = await page.locator('.answer-text').innerText();
    expect(answerText).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
    await expect(page.locator('.answer-citation').first()).toBeVisible();
    if (await page.locator('.answer-citations').count()) {
      await expect(page.locator('.answer-citations')).toContainText('Citations returned with this answer');
    }
    await expect(page.locator('.status-chip').last()).toHaveAttribute('data-status', asked.status);
    const answerKind = asked.answer_kind ?? asked.generation_kind;
    if (answerKind === 'model_synthesis') {
      await expect(page.locator('.status-chip').last()).toContainText('Model synthesis · review sources');
      await expect(page.locator('.answer-provenance')).toContainText(
        String((asked.model as { model: string }).model),
      );
      const markers = [...asked.answer!.matchAll(/\[(\d+)\]/g)];
      expect(markers.length).toBeGreaterThan(0);
      for (const marker of markers) {
        expect(citations.some((citation) => citation.citation_number === Number(marker[1]))).toBeTruthy();
      }
    } else {
      expect(answerKind).toBe('cited_excerpts');
      await expect(page.locator('.status-chip').last()).toContainText('Retrieved material only');
    }
    await expect(page.locator('.source-relevance').first()).toContainText('relative to this query');
    for (const source of citations) {
      expect(
        source.retrieval_score,
        'citation must expose one supported relevance score field',
      ).toBeDefined();
    }
    for (const citation of citations) {
      expect(citation.document_id).toBeTruthy();
      expect(citation.chunk_id).toBeTruthy();
      expect(citation.citation_ref).toBeTruthy();
      await expect(
        page.locator('.source-item strong', { hasText: citation.document_title }).first(),
      ).toHaveText(citation.document_title);
      const docResponse = await page.request.get(`${apiRoot}/documents/${citation.document_id}`, {
        headers: await authHeader(page),
      });
      expect(docResponse.ok()).toBeTruthy();
      const document = await docResponse.json();
      expect(citation.page_number).toBeGreaterThan(0);
      expect(citation.page_number).toBeLessThanOrEqual(document.page_count);
      await expect(
        page
          .getByRole('link', {
            name: `Open ${citation.document_title} · Page ${citation.page_number}`,
          })
          .first(),
      ).toHaveAttribute(
        'href',
        documentPageUrl(citation.document_id, citation.page_number, citation.chunk_id),
      );
    }
    await expect(page.locator('.answer-citation').first()).toBeVisible();
    const largestPageCitation = citations.reduce((largest, current) =>
      current.page_number > largest.page_number ? current : largest,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await capture(page, 'research-desktop-answer-citations');
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'research-mobile-answer-citations', '.turn.assistant');
    for (const citation of citations) {
      await expect(
        page
          .getByRole('link', { name: `Open ${citation.document_title} · Page ${citation.page_number}` })
          .first(),
      ).toBeVisible();
    }
    const sourceGroup = page.locator('details.source-item').first();
    await sourceGroup.locator('summary').click();
    await expect(sourceGroup.locator('.source-excerpt').first()).toBeHidden();
    await sourceGroup.locator('summary').click();
    await expect(sourceGroup.locator('.source-excerpt').first()).toBeVisible();
    await capture(page, 'research-mobile-source-group-expanded', '.sources-card');
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', { name: 'Copy', exact: true }).last().click();
    await expect(page.getByRole('button', { name: 'Copied', exact: true }).last()).toBeVisible();
    await capture(page, 'research-mobile-copy-feedback', '.turn.assistant');
    await page.setViewportSize({ width: 1440, height: 900 });
    const targetCitation = page
      .locator('.answer-citation')
      .filter({ hasText: `Page ${largestPageCitation.page_number}` })
      .first();
    await expect(targetCitation).toHaveAttribute(
      'href',
      documentPageUrl(
        largestPageCitation.document_id,
        largestPageCitation.page_number,
        largestPageCitation.chunk_id,
      ),
    );
    await targetCitation.scrollIntoViewIfNeeded();
    await expect(targetCitation).toBeVisible();
    await targetCitation.click();
    await expect(page).toHaveURL(
      new RegExp(
        `/documents/${encodeURIComponent(largestPageCitation.document_id)}\\?page=${largestPageCitation.page_number}`,
      ),
    );
    await expect(page.getByRole('heading', { name: largestPageCitation.document_title })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'research-mobile-citation-arrival');
    await page.setViewportSize({ width: 1440, height: 900 });
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download PDF' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
    await capture(page, 'research-desktop-citation-viewer');
    await capture(page, 'research-desktop-pdf-downloaded');
  });

  test('an empty case scope returns true no-evidence state', async ({ page }) => {
    const headers = await authHeader(page);
    const [casesResponse, documentsResponse] = await Promise.all([
      page.request.get(`${apiRoot}/cases?page_size=100`, { headers }),
      page.request.get(`${apiRoot}/documents?page_size=100`, { headers }),
    ]);
    expect(casesResponse.ok()).toBeTruthy();
    expect(documentsResponse.ok()).toBeTruthy();
    const cases = (await casesResponse.json()).items as Array<{ id: string; title: string }>;
    const documents = (await documentsResponse.json()).items as Array<{ case_id?: string }>;
    const emptyCase = cases.find(
      (candidate) => !documents.some((document) => document.case_id === candidate.id),
    );
    expect(emptyCase).toBeTruthy();
    await page.getByLabel('Case filter').selectOption(emptyCase!.id);
    const response = await answerQuestion(page, 'What does the case file say about its hearing schedule?');
    expect(['no_evidence', 'insufficient_evidence']).toContain(response.status);
    await expect(page.locator('.state-callout.no-evidence strong')).toHaveText('No supporting excerpts');
    await expect(page.locator('.status-chip[data-status="no_evidence"]')).toHaveText(
      'No supporting excerpts',
    );
    await expect(page.getByText(/Research error/i)).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Upload a document' })).toBeVisible();
    await expect(page.locator('.state-callout.no-evidence .answer-text')).toContainText(
      'No indexed excerpt directly answers this question',
    );
    await expect(page.locator('.state-callout.no-evidence .answer-citation')).toHaveCount(0);
    await page.setViewportSize({ width: 1440, height: 900 });
    await capture(page, 'research-desktop-no-evidence');
    await page.getByRole('link', { name: 'Upload a document' }).click();
    await expect(page).toHaveURL(/\/research\/documents$/);
    await expect(page.getByRole('heading', { name: 'Research library' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Upload a document' })).toBeVisible();
    await capture(page, 'research-desktop-upload-destination');
    await page.goto('/research');
    await waitSettled(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'research-mobile-no-evidence', '.state-callout.no-evidence');
  });

  test('the reachable model can report insufficient evidence without synthesizing a conclusion', async ({
    page,
  }) => {
    const response = await answerQuestion(
      page,
      'What is the governing law of the arbitration agreement itself?',
    );
    expect(['ok', 'answered', 'insufficient_evidence']).toContain(response.status);
    if (response.status === 'insufficient_evidence' || response.answer_basis === 'insufficient_evidence') {
      expect(response.citations ?? response.sources ?? []).toEqual([]);
      expect(response.total).toBe(0);
      await expect(page.locator('.state-callout.no-evidence strong')).toHaveText('No supporting excerpts');
      await expect(page.locator('.status-chip[data-status="no_evidence"]')).toHaveText(
        'No supporting excerpts',
      );
      await expect(page.getByText(/Research error/i)).toHaveCount(0);
      await expect(page.locator('.answer-citations')).toHaveCount(0);
      await expect(page.locator('.source-item')).toHaveCount(0);
      return;
    }
    expect(response.answer).toMatch(/evidence is insufficient/i);
    const insufficiencyCitations = response.citations ?? response.sources ?? [];
    if (response.answer_basis === 'insufficient_evidence' || response.insufficient_evidence) {
      expect(insufficiencyCitations).toEqual([]);
      expect(response.total).toBe(0);
      await expect(page.locator('.state-callout.no-evidence strong')).toHaveText('No supporting excerpts');
      await expect(page.locator('.status-chip[data-status="no_evidence"]')).toHaveText(
        'No supporting excerpts',
      );
      await expect(page.getByText(/Research error/i)).toHaveCount(0);
      await expect(page.locator('.answer-citations')).toHaveCount(0);
      await expect(page.locator('.source-item')).toHaveCount(0);
    } else {
      expect(insufficiencyCitations.length).toBeGreaterThan(0);
      await expect(page.locator('.source-item').first()).toBeVisible();
    }
    await expect(page.getByText('Evidence is insufficient', { exact: true })).toBeVisible();
    await expect(page.getByText(/no conclusion was generated from this evidence/i)).toBeVisible();
    await expect(page.locator('.answer-citations')).toHaveCount(0);
    await page.setViewportSize({ width: 1440, height: 900 });
    await capture(page, 'research-desktop-insufficient-evidence');
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'research-mobile-insufficient-evidence', '.state-callout.no-evidence');
  });

  test('the library upload destination accepts and indexes a real fixture PDF', async ({ page }) => {
    await page.goto('/research/documents');
    await expect(page.getByRole('heading', { name: 'Research library' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Upload a document' })).toBeVisible();
    await capture(page, 'research-desktop-upload-destination');
    const uploadResponse = page.waitForResponse(
      (response) => response.url().endsWith('/ingest/file') && response.request().method() === 'POST',
    );
    const uploadName = `research-upload-${Date.now()}`;
    await page.getByLabel('Choose a document to upload').setInputFiles({
      name: `${uploadName}.pdf`,
      mimeType: 'application/pdf',
      buffer: await import('node:fs/promises').then((fs) =>
        fs.readFile('tests/fixtures/research-upload-fixture.pdf'),
      ),
    });
    const response = await uploadResponse;
    expect(response.ok(), `Upload failed: ${await response.text()}`).toBeTruthy();
    const upload = (await response.json()) as { document_id: string; document: { title: string } };
    expect(upload.document.title).toBe(uploadName);
    const headers = await authHeader(page);
    await expect
      .poll(async () => {
        const job = await page.request.get(`${apiRoot}/documents/${upload.document_id}/job`, { headers });
        if (!job.ok()) return 'unavailable';
        return ((await job.json()) as { status: string }).status;
      })
      .toBe('ready');
    await expect(page.getByRole('status')).toContainText('Document received');
    const documentResponse = await page.request.get(`${apiRoot}/documents/${upload.document_id}`, {
      headers,
    });
    expect(documentResponse.ok()).toBeTruthy();
    const document = await documentResponse.json();
    expect(document.title).toBe(upload.document.title);
    expect(document.status).toBe('ready');
    await capture(page, 'research-desktop-upload-complete');
    const deleteResponse = await page.request.delete(`${apiRoot}/documents/${upload.document_id}`, {
      headers,
    });
    expect(deleteResponse.ok()).toBeTruthy();
  });

  test('unreachable model hides answer text; retry recovers when the configured endpoint is restored', async ({
    page,
  }) => {
    const headers = await authHeader(page);
    const settingsResponse = await page.request.get(`${apiRoot}/settings/ai`, { headers });
    const previous = await settingsResponse.json();
    try {
      await page.request.patch(`${apiRoot}/settings/ai`, {
        headers,
        data: { base_url: 'http://127.0.0.1:1/v1' },
      });
      const failed = await answerQuestion(page, 'What is the seat of arbitration in the agreement?');
      expect(failed.status).toBe('model_unavailable');
      expect(failed.model ?? null).toBeNull();
      const supports = failed.citations ?? failed.sources ?? [];
      expect(supports.length).toBeGreaterThan(0);
      expect(failed.total).toBe(supports.length);
      for (const support of supports) {
        expect(support.document_id).toBeTruthy();
        expect(support.document_title).toBeTruthy();
        expect(support.page_number).toBeGreaterThan(0);
        expect(support.chunk_id).toBeTruthy();
      }
      expect(failed.answer ?? '').not.toMatch(/Mumbai|Chennai|governing law/i);
      await expect(page.getByText('Model unavailable', { exact: true })).toBeVisible();
      await expect(page.locator('.state-callout.no-evidence .answer-text')).toHaveCount(0);
      await expect(page.getByText('Lexical results · documents only')).toBeVisible();
      const callout = page.locator('.state-callout.unavailable').filter({ hasText: 'Model unavailable' });
      const calloutText = await callout.innerText();
      expect(calloutText).not.toMatch(/https?:\/\//i);
      expect(calloutText).not.toContain('127.0.0.1');
      expect(calloutText).not.toMatch(/\b\d{2,5}\b/);
      await page.setViewportSize({ width: 1440, height: 900 });
      await capture(page, 'research-desktop-model-unavailable');
      await page.setViewportSize({ width: 390, height: 844 });
      await capture(page, 'research-mobile-model-unavailable', '.state-callout.unavailable');

      await page.request.patch(`${apiRoot}/settings/ai`, {
        headers,
        data: { base_url: previous.base_url, model: previous.model },
      });
      const retryPromise = page.waitForResponse(
        (response) => response.url().endsWith('/api/v1/ai/ask') && response.request().method() === 'POST',
      );
      await page.getByRole('button', { name: 'Retry' }).first().click();
      const retryResponse = await retryPromise;
      const recovered = await retryResponse.json();
      expect(['ok', 'answered']).toContain(recovered.status);
      expect(String(recovered.answer ?? '').trim().length).toBeGreaterThan(0);
      await expect(page.locator('.answer-citation').first()).toBeVisible();
      await capture(page, 'research-desktop-retry-recovered');
    } finally {
      await page.request.patch(`${apiRoot}/settings/ai`, {
        headers,
        data: { base_url: previous.base_url, model: previous.model },
      });
    }
  });
});

test('research answer normalization preserves the source status and canonicalizes both insufficient values', () => {
  for (const raw_status of ['no_evidence', 'insufficient_evidence']) {
    const normalized = normalizeResearchAnswer({
      status: raw_status,
      answer: 'No indexed excerpt directly answers this question.',
    });
    expect(normalized.status).toBe('no_evidence');
    expect(normalized.raw_status).toBe(raw_status);
  }
  const unavailable = normalizeResearchAnswer({
    status: 'model_unavailable',
    answer: 'The search could not be completed because the configured language model is unavailable.',
    insufficient_evidence: true,
  });
  expect(unavailable.status).toBe('model_unavailable');
  expect(unavailable.raw_status).toBe('model_unavailable');
});

test('strategy API normalization preserves raw status and canonicalizes no-evidence values', () => {
  const normalized = normalizeStrategyData({
    status: 'insufficient_evidence',
    case_theory: '',
    key_issues: [],
    legal_arguments: [],
    counterarguments: [],
    evidence_gaps: [],
    strategy_plan: '',
    updated_at: null,
    model: null,
    citations: [],
    assertion_citations: [],
    manually_edited: false,
    generation_note: '',
  });
  expect(normalized.status).toBe('no_evidence');
  expect(normalized.raw_status).toBe('insufficient_evidence');
});

test('dashboard ask API boundary canonicalizes insufficient evidence and keeps raw status', () => {
  const normalized = normalizeAskResponse({
    status: 'insufficient_evidence',
    answer: 'No indexed excerpt directly answers this question.',
    citations: [],
    follow_ups: [],
  });
  expect(normalized.status).toBe('no_evidence');
  expect(normalized.raw_status).toBe('insufficient_evidence');
});
