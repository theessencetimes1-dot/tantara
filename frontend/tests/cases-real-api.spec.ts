import { test, expect } from '@playwright/test';
import { requirePlaywrightApi } from './api-readiness';
const base = `${process.env.TANTARA_API_ORIGIN || 'http://127.0.0.1:8010'}/api/v1`;
test.beforeAll(async () => requirePlaywrightApi());
test('real API workflow persists client, case, party, hearing and task', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
    password = process.env.TANTARA_E2E_PASSWORD || 'tantara-local';
  const login = await request.post(`${base}/auth/login`, {
    data: { email, password },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = Date.now().toString();
  let clientId = '',
    caseId = '',
    taskId = '',
    hearingId = '';
  const post = async (path: string, data: unknown) => {
    const r = await request.post(`${base}${path}`, { headers, data });
    expect(r.ok(), `${path} should accept workflow data: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  const del = async (path: string) => {
    if (path)
      try {
        await request.delete(`${base}${path}`, { headers, timeout: 5000 });
      } catch {
        /* cleanup should not hide a completed persistence assertion if the test API stops */
      }
  };
  try {
    const client = await post('/clients', {
      name: `E2E Client ${suffix}`,
      email: `e2e-${suffix}@example.test`,
    });
    clientId = client.id;
    const matter = await post('/cases', {
      title: `E2E Matter ${suffix}`,
      client_id: clientId,
      claimant: 'E2E Claimant',
      respondent: 'E2E Respondent',
      forum: 'SIAC',
      status: 'active',
    });
    caseId = matter.id;
    await post(`/cases/${caseId}/participants`, {
      name: 'E2E Counsel',
      party_role: 'counsel',
      email: `counsel-${suffix}@example.test`,
    });
    const hearing = await post('/hearings', {
      title: `E2E Hearing ${suffix}`,
      case_id: caseId,
      at: new Date(Date.now() + 86400000).toISOString(),
      mode: 'online',
    });
    hearingId = hearing.id;
    const task = await post('/tasks', {
      title: `E2E Task ${suffix}`,
      case_id: caseId,
      due_at: new Date(Date.now() + 86400000).toISOString(),
      priority: 'high',
      status: 'todo',
    });
    taskId = task.id;
    await page.addInitScript(
      ({ tokenValue }) => {
        localStorage.setItem('tantara_token', tokenValue);
        document.cookie = `tantara_token=${tokenValue}; Path=/; SameSite=Lax`;
      },
      { tokenValue: token },
    );
    await page.setViewportSize({ width: 1440, height: 950 });
    await page.goto('/cases');
    await page.getByRole('textbox', { name: 'Search cases' }).fill(`E2E Matter ${suffix}`);
    await expect(page.getByRole('link', { name: `E2E Matter ${suffix}` })).toBeVisible();
    await page.getByRole('button', { name: /Case Title/ }).click();
    await page.reload();
    await page.getByRole('textbox', { name: 'Search cases' }).fill(`E2E Matter ${suffix}`);
    await expect(page.getByRole('link', { name: `E2E Matter ${suffix}` })).toBeVisible();
    const persisted = await request.get(`${base}/cases?q=${encodeURIComponent(`E2E Matter ${suffix}`)}`, {
      headers,
    });
    expect((await persisted.json()).items[0].id).toBe(caseId);
    const participants = await request.get(`${base}/cases/${caseId}/overview`, {
      headers,
    });
    expect(participants.ok()).toBeTruthy();

    await page.goto(`/cases/${caseId}`);
    const caseTabs = page.getByRole('tablist', { name: 'Case sections' });
    const overviewTab = caseTabs.getByRole('tab', { name: 'Overview' });
    const casePanel = page.getByRole('tabpanel');
    const casePanelId = (await casePanel.getAttribute('id'))!;
    const overviewTabId = (await overviewTab.getAttribute('id'))!;
    await expect(overviewTab).toHaveAttribute('aria-controls', casePanelId);
    await expect(casePanel).toHaveAttribute('aria-labelledby', overviewTabId);
    await expect(caseTabs.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('tabindex', '-1');
    await overviewTab.focus();
    await overviewTab.press('ArrowRight');
    const timelineTab = caseTabs.getByRole('tab', { name: 'Timeline' });
    await expect(timelineTab).toHaveAttribute('aria-selected', 'true');
    await expect(timelineTab).toHaveAttribute('tabindex', '0');
    await expect(timelineTab).toBeFocused();
    await expect(casePanel).toHaveAttribute('aria-labelledby', (await timelineTab.getAttribute('id'))!);

    const strategyTab = caseTabs.getByRole('tab', { name: 'Strategy' });
    await strategyTab.click();
    const embeddedTabs = page.getByRole('tablist', { name: 'Case strategy sections' });
    const embeddedTheory = embeddedTabs.getByRole('tab', { name: 'Case Theory' });
    const embeddedPanelId = (await embeddedTheory.getAttribute('aria-controls'))!;
    const embeddedPanel = page.locator(`[id="${embeddedPanelId}"]`);
    await expect(embeddedPanel).toHaveAttribute(
      'aria-labelledby',
      (await embeddedTheory.getAttribute('id'))!,
    );
    await embeddedTheory.focus();
    await embeddedTheory.press('ArrowRight');
    const embeddedIssues = embeddedTabs.getByRole('tab', { name: 'Key Issues' });
    await expect(embeddedIssues).toHaveAttribute('aria-selected', 'true');
    await expect(embeddedIssues).toBeFocused();
    await expect(embeddedPanel).toHaveAttribute(
      'aria-labelledby',
      (await embeddedIssues.getAttribute('id'))!,
    );

    await page.goto(`/strategy?case_id=${caseId}&tab=Case%20Theory`);
    const strategyTabs = page.getByRole('tablist', { name: 'Strategy sections' });
    const theoryTab = strategyTabs.getByRole('tab', { name: 'Case Theory' });
    const strategyPanel = page.getByRole('tabpanel');
    await expect(theoryTab).toHaveAttribute('aria-controls', (await strategyPanel.getAttribute('id'))!);
    await expect(strategyPanel).toHaveAttribute('aria-labelledby', (await theoryTab.getAttribute('id'))!);
    await theoryTab.focus();
    await theoryTab.press('ArrowRight');
    const issuesTab = strategyTabs.getByRole('tab', { name: 'Key Issues' });
    await expect(issuesTab).toHaveAttribute('aria-selected', 'true');
    await expect(issuesTab).toBeFocused();
    await expect(page).toHaveURL(/tab=Key\+Issues|tab=Key%20Issues/);
    await expect(strategyPanel).toHaveAttribute('aria-labelledby', (await issuesTab.getAttribute('id'))!);
  } finally {
    await del(taskId ? `/tasks/${taskId}` : '');
    await del(hearingId ? `/hearings/${hearingId}` : '');
    await del(caseId ? `/cases/${caseId}` : '');
    await del(clientId ? `/clients/${clientId}` : '');
  }
});
test('new case routes remain usable without horizontal overflow at target widths', async ({
  page,
  request,
}) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  const errors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/cases');
    await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      `overflow at ${width}`,
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test('case detail reports an unreadable id with a retryable not-found state', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto(`/cases/not-a-real-case-${Date.now()}`);
  await expect(page.getByRole('heading', { name: 'Case not found' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('closed status restores from URL and table sorting toggles direction accessibly', async ({
  page,
  request,
}) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/cases?status=closed');
  await expect(page.getByRole('button', { name: /Closed/ })).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/cases');
  const title = page.getByRole('button', { name: /Case Title/ });
  await title.click();
  await expect(page.locator('th').filter({ has: title })).toHaveAttribute('aria-sort', 'ascending');
  await title.click();
  await expect(page.locator('th').filter({ has: title })).toHaveAttribute('aria-sort', 'descending');
});

test('calendar week view renders seven distinct dates', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/calendar');
  await page.getByRole('button', { name: 'Week' }).click();
  await expect.poll(() => page.locator('[data-calendar-day]').count()).toBe(7);
  expect(
    await page
      .locator('[data-calendar-day]')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-calendar-day'))),
  ).toHaveLength(7);
});

test('mobile cases keep title, hearing and status inside the viewport', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/cases');
  const card = page.locator('.matter-mobile-case').first();
  await expect(card).toBeVisible();
  await expect(card.locator('.status-pill')).toBeVisible();
  await expect(card).toContainText('Next hearing:');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const box = await card.boundingBox();
  expect(box).toBeTruthy();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
});

test('calendar mobile defaults to readable agenda view', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/calendar');
  await expect(page.getByRole('button', { name: 'Agenda' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator("[data-calendar-agenda-settled='true']")).toBeVisible();
  const monthStart = new Date();
  monthStart.setDate(1);
  const nextMonthStart = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 1);
  const from = monthStart.toISOString().slice(0, 10);
  const to = nextMonthStart.toISOString().slice(0, 10);
  const calendarResponse = await request.get(`${base}/calendar?from=${from}&to=${to}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(calendarResponse.ok()).toBeTruthy();
  const apiEvents = (await calendarResponse.json()) as Array<{ at: string }>;
  const datedEventCount = new Set(
    apiEvents.map((event) =>
      new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(new Date(event.at)),
    ),
  ).size;
  if (datedEventCount > 7) {
    const firstPageHeading = await page.locator('.calendar-agenda > section h2').first().innerText();
    await page.getByRole('button', { name: 'Next days' }).click();
    await expect(page.locator('.calendar-agenda > section')).toHaveCount(7);
    expect(await page.locator('.calendar-agenda > section h2').first().innerText()).not.toBe(
      firstPageHeading,
    );
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(await page.locator('.calendar-agenda > section').count()).toBeLessThanOrEqual(7);
  await page.locator('.calendar-agenda-row').first().click();
  await expect(page.getByRole('dialog', { name: 'Event details' })).toBeVisible();
  expect(
    await page
      .locator('.calendar-agenda-row span')
      .evaluateAll((nodes) =>
        nodes.every(
          (node) =>
            getComputedStyle(node).overflowWrap !== 'anywhere' &&
            getComputedStyle(node).wordBreak !== 'break-all',
        ),
      ),
  ).toBeTruthy();
});

test('task Retry recovers when the API responds again', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
    const originalFetch = window.fetch.bind(window);
    let failuresRemaining = 2;
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (failuresRemaining > 0 && new URL(url, location.href).pathname.endsWith('/api/v1/tasks')) {
        failuresRemaining -= 1;
        return Promise.resolve(
          new Response(JSON.stringify({ error: { message: 'temporary failure' } }), {
            status: 503,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }
      return originalFetch(input, init);
    };
  }, token);
  await page.goto('/tasks');
  await expect(page.locator('.matter-error')).toBeVisible();
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.locator('.task-groups')).toBeVisible();
  await expect(page.locator('.matter-error')).toHaveCount(0);
});

test('case, calendar and client routes each expose one active navigation link', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  const listing = await request.get(`${base}/cases?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const caseId = (await listing.json()).items[0].id as string;
  const clients = await request.get(`${base}/clients?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const clientId = (await clients.json()).items[0].id as string;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  for (const route of [
    '/cases',
    `/cases/${caseId}`,
    '/clients',
    `/clients/${clientId}`,
    '/tasks',
    '/calendar',
  ]) {
    await page.goto(route);
    await expect(page.locator('.nav a[aria-current="page"]')).toHaveCount(1);
    await expect(page.locator('.nav a')).toHaveCount(14);
    if (route.startsWith('/clients/')) {
      const current = page.locator('.nav a[aria-current="page"]');
      await expect(current).toHaveAttribute('href', '/clients');
      await expect(current).toContainText('Clients');
    }
  }
});

test('mobile task actions remain available and open a labelled menu', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/tasks');
  const row = page.locator('.task-row').first();
  await expect(row.locator('.task-case')).not.toHaveText('Linked case');
  const actions = row.getByRole('button', { name: /^Actions for / });
  await expect(actions).toBeVisible();
  await actions.click();
  await expect(row.getByRole('button', { name: 'Edit' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
