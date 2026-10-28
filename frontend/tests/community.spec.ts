import { expect, test, APIRequestContext, Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const backend = `${process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010'}/api/v1`;
const captures = resolve(process.cwd(), '../captures-fe7');
mkdirSync(captures, { recursive: true });

type UserLogin = { access_token: string; user: { id: string; name: string; email: string; role: string } };
type Post = {
  id: string;
  title: string;
  body: string;
  visibility: string;
  author_name?: string;
  author_role?: string;
  is_demo?: boolean;
  tags?: string[];
};

async function login(request: APIRequestContext, email: string): Promise<UserLogin> {
  const response = await request.post(`${backend}/auth/login`, {
    data: { email, password: 'tantara-local' },
  });
  expect(response.status(), `login ${email}`).toBe(200);
  return response.json();
}

async function api(
  request: APIRequestContext,
  token: string | undefined,
  path: string,
  options: { method?: string; data?: unknown } = {},
) {
  return request.fetch(`${backend}${path}`, {
    method: options.method ?? 'GET',
    data: options.data,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

async function openAuthenticated(page: Page, identity: UserLogin, route = '/community') {
  await page.addInitScript((token) => localStorage.setItem('tantara_token', token), identity.access_token);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(route);
  const me = await api(page.request, identity.access_token, '/auth/me');
  expect(me.status(), 'authenticated before page capture').toBe(200);
  const activeLabel = route.startsWith('/settings/') ? 'Settings' : 'Community';
  await expect(
    page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: activeLabel }),
  ).toHaveAttribute('aria-current', 'page');
  if (route === '/community') await expect(page.getByRole('heading', { name: 'Community' })).toBeVisible();
  else if (route.startsWith('/settings/'))
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  else await expect(page.locator('.community-thread')).toBeVisible();
}

async function capture(page: Page, name: string, fullPage = false) {
  await page.screenshot({ path: resolve(captures, name), fullPage });
}

test('seeded feed, navigation, and tag filter render at desktop and mobile sizes', async ({
  page,
  request,
}) => {
  const user = await login(request, 'advocate@tantara.local');
  const response = await api(request, user.access_token, '/community/posts?page=1&page_size=100');
  expect(response.status()).toBe(200);
  const feed = await response.json();
  expect(feed.total).toBeGreaterThan(0);
  expect(feed.items[0]).toHaveProperty('author_name');
  expect(feed.items[0]).toHaveProperty('created_at');
  console.log(`Community item keys: ${Object.keys(feed.items[0]).sort().join(', ')}`);
  await openAuthenticated(page, user);
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await nav.getByRole('link', { name: 'Community' }).click();
  await expect(nav.getByRole('link', { name: 'Community' })).toHaveAttribute('aria-current', 'page');
  await page.getByLabel('Search discussions').fill('Demo');
  const demoSearch = page.waitForResponse(
    (item) =>
      item.request().method() === 'GET' &&
      item.url().includes('/community/posts?') &&
      item.url().includes('q=Demo'),
  );
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  const demoResponse = await demoSearch;
  expect(demoResponse.status()).toBe(200);
  const demos = await demoResponse.json();
  expect(demos.items.length).toBeGreaterThan(0);
  expect(demos.items.every((post: Post) => post.is_demo)).toBeTruthy();
  await expect(page.getByText('Demo content').first()).toBeVisible();
  await page.locator('.community-feed').scrollIntoViewIfNeeded();
  await capture(page, 'community-feed-seeded-desktop-1440x900.png');

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= 390),
    '390px feed horizontal overflow',
  ).toBeTruthy();
  await capture(page, 'community-feed-seeded-mobile-390x844.png');

  const tag = page.getByRole('button', { name: 'construction', exact: true });
  await expect(tag).toBeVisible();
  const filtered = page.waitForResponse(
    (item) => item.url().includes('/community/posts?') && item.url().includes('tag=construction'),
  );
  await tag.click();
  expect((await filtered).status()).toBe(200);
  await expect(tag).toHaveAttribute('aria-pressed', 'true');
  const titles = await page.locator('.community-post').allTextContents();
  expect(titles.length).toBeGreaterThan(0);
  for (const title of titles) expect(title.toLowerCase()).toContain('construction');
  await capture(page, 'community-feed-filtered-construction-mobile-390x844.png');
});

test('thread shows API authors and real reply total at desktop and mobile sizes', async ({
  page,
  request,
}) => {
  const user = await login(request, 'advocate@tantara.local');
  const list = await api(request, user.access_token, '/community/posts?page=1&page_size=100');
  const posts: Post[] = (await list.json()).items;
  let selected: Post | undefined;
  let count = 0;
  for (const post of posts) {
    if (!post.is_demo) continue;
    const response = await api(request, user.access_token, `/community/posts/${post.id}/replies`);
    const data = await response.json();
    if (data.total > 0) {
      selected = post;
      count = data.total;
      break;
    }
  }
  expect(selected, 'seed includes a post with replies').toBeTruthy();
  await openAuthenticated(page, user, `/community/${selected!.id}`);
  await expect(page.getByRole('heading', { name: `Replies (${count})` })).toBeVisible();
  await expect(page.locator('.community-byline').first()).toContainText(selected!.author_name!);
  await expect(page.locator('.community-byline').first()).toContainText('Asia/Kolkata');
  await capture(page, 'community-detail-replies-desktop-1440x900.png');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= 390),
    '390px detail horizontal overflow',
  ).toBeTruthy();
  await capture(page, 'community-detail-replies-mobile-390x844.png');
});

test('composer success is confirmed by a fresh API list response and validation errors are inline', async ({
  page,
  request,
}) => {
  const user = await login(request, 'advocate@tantara.local');
  await openAuthenticated(page, user);
  const title = `Round 2 API post ${Date.now()}`;
  await page.getByLabel('Title', { exact: true }).fill(title);
  await page.getByLabel('Details').fill('Created through the real community composer for verification.');
  await page.getByLabel('Tags').fill('verification, construction');
  await page.getByLabel('Visibility').selectOption('workspace');
  const refreshed = page.waitForResponse(
    (response) => response.request().method() === 'GET' && response.url().includes('/community/posts?'),
  );
  await page.getByRole('button', { name: 'Post discussion' }).click();
  const listResponse = await refreshed;
  expect(listResponse.status()).toBe(200);
  const body = await listResponse.json();
  const created = body.items.find((item: Post) => item.title === title);
  expect(created, 'new title came back from the API after posting').toBeTruthy();
  expect(created.author_name).toBe(user.user.name);
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await expect(page.getByText(user.user.name).first()).toBeVisible();
  await page.locator('.community-feed').scrollIntoViewIfNeeded();
  await capture(page, 'community-composer-success-desktop-1440x900.png');

  await page.locator('#community-title').fill('x'.repeat(301));
  await page.locator('#community-body').fill('Expected API validation failure.');
  const invalid = page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/community/posts'),
  );
  await page.getByRole('button', { name: 'Post discussion' }).click();
  expect((await invalid).status()).toBe(422);
  await expect(page.locator('.community-error')).toContainText('validation_error');
  await expect(page.locator('#community-title')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#community-title-error')).toContainText('300 characters');
  await capture(page, 'community-composer-validation-desktop-1440x900.png');
});

test('reply submission at mobile width increments the API total by exactly one', async ({
  page,
  request,
}) => {
  const user = await login(request, 'advocate@tantara.local');
  const created = await api(request, user.access_token, '/community/posts', {
    method: 'POST',
    data: {
      title: `Mobile reply count ${Date.now()}`,
      body: 'Post for measuring a reply count from the replies endpoint.',
      kind: 'discussion',
      visibility: 'workspace',
      tags: ['mobile-verification'],
    },
  });
  expect(created.status()).toBe(200);
  const post: Post = await created.json();
  const beforeResponse = await api(request, user.access_token, `/community/posts/${post.id}/replies`);
  const before = await beforeResponse.json();
  await openAuthenticated(page, user, `/community/${post.id}`);
  await page.setViewportSize({ width: 390, height: 844 });
  const uniqueReply = `Unique mobile reply ${Date.now()}`;
  await page.getByLabel('Add a reply').fill(uniqueReply);
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith(`/community/posts/${post.id}/replies`),
  );
  await page.getByRole('button', { name: 'Reply' }).click();
  expect((await posted).status()).toBe(200);
  await expect(page.getByRole('heading', { name: `Replies (${before.total + 1})` })).toBeVisible();
  await expect(page.getByText(uniqueReply)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 390)).toBeTruthy();
  await page.getByText(uniqueReply).scrollIntoViewIfNeeded();
  await capture(page, 'community-reply-submitted-mobile-390x844.png');
});

test('empty search state is the real filtered staff response and includes the composer action', async ({
  page,
  request,
}) => {
  const user = await login(request, 'staff@tantara.local');
  const emptyQuery = 'no-match-community-verification-20261028';
  const response = await api(
    request,
    user.access_token,
    `/community/posts?page=1&page_size=100&q=${emptyQuery}`,
  );
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.total).toBe(0);
  await openAuthenticated(page, user);
  await page.getByLabel('Search discussions').fill(emptyQuery);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No matching discussions' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Post discussion' })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await capture(page, 'community-empty-search-staff-desktop-1440x900.png', true);
});

test('save state persists and is isolated per user; visibility and reply authorization are enforced', async ({
  request,
}) => {
  const advocate = await login(request, 'advocate@tantara.local');
  const researcher = await login(request, 'researcher@tantara.local');
  const staff = await login(request, 'staff@tantara.local');
  const anonymous = await api(request, undefined, '/community/posts?page=1&page_size=10');
  expect(anonymous.status(), 'anonymous list').toBe(401);

  const privatePostResponse = await api(request, advocate.access_token, '/community/posts', {
    method: 'POST',
    data: {
      title: `Private visibility ${Date.now()}`,
      body: 'Private post authorization check.',
      kind: 'question',
      visibility: 'private',
      tags: ['round-two'],
    },
  });
  expect(privatePostResponse.status(), 'create private post').toBe(200);
  const privatePost: Post = await privatePostResponse.json();
  const privateDetail = await api(request, researcher.access_token, `/community/posts/${privatePost.id}`);
  expect(privateDetail.status(), 'other user private detail').toBe(404);
  const researcherFeed = await api(request, researcher.access_token, '/community/posts?page=1&page_size=100');
  expect((await researcherFeed.json()).items.some((item: Post) => item.id === privatePost.id)).toBeFalsy();

  const workspaceResponse = await api(request, advocate.access_token, '/community/posts', {
    method: 'POST',
    data: {
      title: `Workspace authorization ${Date.now()}`,
      body: 'Shared post for reply and save checks.',
      kind: 'discussion',
      visibility: 'workspace',
      tags: ['round-two'],
    },
  });
  expect(workspaceResponse.status(), 'create workspace post').toBe(200);
  const workspacePost: Post = await workspaceResponse.json();
  const workspaceDetail = await api(request, researcher.access_token, `/community/posts/${workspacePost.id}`);
  expect(workspaceDetail.status(), 'other user workspace detail').toBe(200);

  const replyResponse = await api(
    request,
    researcher.access_token,
    `/community/posts/${workspacePost.id}/replies`,
    { method: 'POST', data: { body: 'Reply owned by researcher for deletion authorization.' } },
  );
  expect(replyResponse.status(), 'create reply').toBe(200);
  const reply = await replyResponse.json();
  const forbiddenDelete = await api(
    request,
    advocate.access_token,
    `/community/posts/${workspacePost.id}/replies/${reply.id}`,
    { method: 'DELETE' },
  );
  expect(forbiddenDelete.status(), 'another user deleting reply').toBe(403);
  const ownDelete = await api(
    request,
    researcher.access_token,
    `/community/posts/${workspacePost.id}/replies/${reply.id}`,
    { method: 'DELETE' },
  );
  expect(ownDelete.status(), 'reply owner deletion').toBe(200);

  const savedByAdvocate = await api(
    request,
    advocate.access_token,
    `/community/posts/${workspacePost.id}/save`,
    { method: 'POST' },
  );
  expect(savedByAdvocate.status(), 'first save').toBe(200);
  expect((await savedByAdvocate.json()).saved).toBe(true);
  const researcherSavedBefore = await api(
    request,
    researcher.access_token,
    '/community/posts?saved=true&page_size=100',
  );
  expect(
    (await researcherSavedBefore.json()).items.some((item: Post) => item.id === workspacePost.id),
  ).toBeFalsy();
  const savedByResearcher = await api(
    request,
    researcher.access_token,
    `/community/posts/${workspacePost.id}/save`,
    { method: 'POST' },
  );
  expect(savedByResearcher.status(), 'second user save').toBe(200);
  expect((await savedByResearcher.json()).saved).toBe(true);
  const unsavedByAdvocate = await api(
    request,
    advocate.access_token,
    `/community/posts/${workspacePost.id}/save`,
    { method: 'POST' },
  );
  expect((await unsavedByAdvocate.json()).saved).toBe(false);
  const advocateSaved = await api(
    request,
    advocate.access_token,
    '/community/posts?saved=true&page_size=100',
  );
  const researcherSaved = await api(
    request,
    researcher.access_token,
    '/community/posts?saved=true&page_size=100',
  );
  expect((await advocateSaved.json()).items.some((item: Post) => item.id === workspacePost.id)).toBeFalsy();
  expect(
    (await researcherSaved.json()).items.some((item: Post) => item.id === workspacePost.id),
  ).toBeTruthy();

  const staffDetail = await api(request, staff.access_token, `/community/posts/${workspacePost.id}`);
  expect(staffDetail.status(), 'workspace visibility applies across all workspace users').toBe(200);
  console.log(
    'Observed authorization statuses: anonymous list 401; private cross-user detail 404; foreign reply delete 403; workspace cross-user detail 200; save per-user verified.',
  );
});

test('saved thread remains saved after reload', async ({ page, request }) => {
  const user = await login(request, 'advocate@tantara.local');
  const created = await api(request, user.access_token, '/community/posts', {
    method: 'POST',
    data: {
      title: `Saved persistence ${Date.now()}`,
      body: 'Dedicated workspace post for persisted save state.',
      kind: 'discussion',
      visibility: 'workspace',
      tags: ['save-verification'],
    },
  });
  expect(created.status()).toBe(200);
  const workspacePost: Post = await created.json();
  await openAuthenticated(page, user, `/community/${workspacePost.id}`);
  const response = page.waitForResponse(
    (item) =>
      item.request().method() === 'POST' && item.url().endsWith(`/community/posts/${workspacePost.id}/save`),
  );
  await page.getByRole('button', { name: 'Save discussion' }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('button', { name: 'Unsave discussion' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Unsave discussion' })).toBeVisible();
  await capture(page, 'community-saved-persisted-desktop-1440x900.png');
});

test('corpus import panel renders the live response shape', async ({ page, request }) => {
  const user = await login(request, 'advocate@tantara.local');
  const response = await api(request, user.access_token, '/settings/data/import');
  expect(response.status()).toBe(200);
  const manifest = await response.json();
  expect(manifest).toHaveProperty('status');
  expect(manifest).toHaveProperty('items');
  await openAuthenticated(page, user, '/settings/data-import');
  await expect(page.getByRole('heading', { name: 'Corpus manifest' })).toBeVisible();
  await expect(page.locator('body')).toContainText(String(manifest.status));
  await capture(page, 'settings-data-manifest-desktop-1440x900.png');
});

test('public corpus import is accepted, polled, and displays recorded outcomes', async ({
  page,
  request,
}) => {
  test.setTimeout(360000);
  const user = await login(request, 'advocate@tantara.local');
  await openAuthenticated(page, user, '/settings/data-import');
  page.on('dialog', (dialog) => dialog.accept());
  const started = page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/settings/data/import'),
  );
  await page.getByRole('button', { name: 'Import public legal corpus' }).click();
  const accepted = await started;
  expect(accepted.status()).toBe(202);
  await expect(page.getByRole('status')).toContainText('Import is in progress');
  await capture(page, 'settings-corpus-import-running-desktop-1440x900.png');

  let terminal: { status: string; items: Array<Record<string, unknown>> } | undefined;
  await expect
    .poll(
      async () => {
        const response = await api(request, user.access_token, '/settings/data/import');
        if (response.status() !== 200) return 'http-error';
        const value = await response.json();
        if (value.status === 'complete') terminal = value;
        return value.status;
      },
      { timeout: 330000, intervals: [2500, 5000, 10000] },
    )
    .toBe('complete');
  expect(terminal).toBeTruthy();
  expect(terminal!.items.length).toBeGreaterThan(0);
  await expect(page.locator('body')).toContainText(String(terminal!.items[0].title), { timeout: 30000 });
  await capture(page, 'settings-corpus-import-result-desktop-1440x900.png', true);

  const indexed = terminal!.items.find(
    (item) => item.status === 'indexed' || item.status === 'already_indexed',
  );
  const failed = terminal!.items.find((item) => item.status === 'failed');
  if (indexed) {
    const card = page
      .locator('.card')
      .filter({ hasText: String(indexed.title) })
      .first();
    await expect(card).toContainText(String(indexed.status));
    await card.scrollIntoViewIfNeeded();
    await capture(page, 'settings-corpus-source-indexed-desktop-1440x900.png');
  }
  if (failed) {
    expect(typeof failed.reason).toBe('string');
    const card = page
      .locator('.card')
      .filter({ hasText: String(failed.title) })
      .first();
    await expect(card).toContainText(String(failed.reason));
    await card.scrollIntoViewIfNeeded();
    await capture(page, 'settings-corpus-source-failed-desktop-1440x900.png');
  }
  console.log(
    `Corpus import status=${terminal!.status}, indexed=${terminal!.items.filter((item) => item.status === 'indexed' || item.status === 'already_indexed').length}, failed=${terminal!.items.filter((item) => item.status === 'failed').length}`,
  );
});

test('offline state explains the failed request and retry recovers when connectivity returns', async ({
  page,
  request,
}) => {
  const user = await login(request, 'advocate@tantara.local');
  await openAuthenticated(page, user);
  await page.context().setOffline(true);
  await page.getByLabel('Search discussions').fill('offline retry check');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.locator('.offline')).toContainText('Community API is unavailable');
  await expect(page.locator('.offline').getByRole('button', { name: 'Retry' })).toBeVisible();
  await capture(page, 'community-offline-error-desktop-1440x900.png');
  await page.context().setOffline(false);
  await page.locator('.offline').getByRole('button', { name: 'Retry' }).click();
  await expect(page.locator('.offline')).toHaveCount(0);
  await expect(page.getByLabel('Search discussions')).toHaveValue('offline retry check');
  console.log('Offline copy and retry verified against the live backend after network recovery.');
});
