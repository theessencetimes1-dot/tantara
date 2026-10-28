import { test, expect } from '@playwright/test';
import { taskGroup } from '../src/features/tasks/grouping';
import { matterStatusClass } from '../src/features/cases/status';
import { displayClientStatus } from '../src/features/clients/status';
import {
  WORKSPACE_TIME_ZONE,
  calendarDay,
  workspaceDateKey,
  workspaceDateTimeInput,
  workspaceDateTimeIso,
} from '../src/lib/datetime';
import { test as browserTest, expect as browserExpect } from '@playwright/test';
import { requirePlaywrightApi } from './api-readiness';
const base = `${process.env.TANTARA_API_ORIGIN || 'http://127.0.0.1:8010'}/api/v1`;
test.beforeAll(async () => requirePlaywrightApi());

test('tasks partition into exclusive workspace-timezone groups including undated open work', () => {
  const now = new Date('2026-10-27T09:00:00Z'); // 14:30 in Asia/Kolkata
  const group = (status: string, due_at?: string | null) => taskGroup({ status, due_at }, now);
  expect(group('open', '2026-10-26T23:00:00+05:30')).toBe('Overdue');
  expect(group('open', '2026-10-27T18:00:00+05:30')).toBe('Today');
  expect(group('open', '2026-10-30T10:00:00+05:30')).toBe('This week');
  expect(group('open', '2026-11-02T10:00:00+05:30')).toBe('Later');
  expect(group('open', null)).toBe('No due date');
  expect(group('done', null)).toBe('Done');
});

test('workspace datetime editing preserves zoned wall time and civil calendar days', () => {
  expect(WORKSPACE_TIME_ZONE).toBe('Asia/Kolkata');
  expect(workspaceDateTimeInput('2026-10-27T04:30:00Z')).toBe('2026-10-27T10:00');
  expect(workspaceDateTimeIso('2026-10-27T10:00')).toBe('2026-10-27T10:00:00+05:30');
  expect(workspaceDateKey('2026-10-27')).toBe('2026-10-27');
  const civil = calendarDay(2026, 9, 27);
  expect(civil.getUTCDate()).toBe(27);
  expect(workspaceDateKey('2026-10-26T20:00:00Z')).toBe('2026-10-27');
});

test('case status classes use semantic colors only for known statuses', () => {
  expect(matterStatusClass('active')).toBe('active');
  expect(matterStatusClass('pending')).toBe('pending');
  expect(matterStatusClass('closed')).toBe('closed');
  expect(matterStatusClass('review')).toBe('unknown');
  expect(matterStatusClass(undefined)).toBe('unknown');
});

test('missing client status remains unavailable instead of being inferred', () => {
  expect(displayClientStatus(undefined)).toBe('—');
  expect(displayClientStatus('inactive')).toBe('inactive');
});

browserTest('activity feed does not masquerade as an unread signal', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  browserExpect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/cases');
  await page.getByRole('button', { name: 'Recent activity' }).click();
  browserExpect(await page.locator('.activity-dot').count()).toBe(0);
});

browserTest('task wall time stays in the workspace zone inside a UTC browser', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: { email: 'advocate@tantara.local', password: 'tantara-local' },
  });
  browserExpect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const task = await request.post(`${base}/tasks`, {
    headers,
    data: { title: 'Workspace wall time check', due_at: '2027-02-03T10:00:00+05:30' },
  });
  browserExpect(task.ok()).toBeTruthy();
  const deadline = await request.post(`${base}/tasks`, {
    headers,
    data: { title: 'Workspace midnight deadline check', due_at: '2027-02-03T00:00:00+05:30' },
  });
  browserExpect(deadline.ok()).toBeTruthy();
  try {
    await page.addInitScript((value) => {
      localStorage.setItem('tantara_token', value);
      document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
    }, token);
    await page.goto('/tasks');
    const row = page.locator('.task-row').filter({ hasText: 'Workspace wall time check' });
    await browserExpect(row).toBeVisible();
    await browserExpect(row.locator('.task-due')).toContainText('10:00');
    await browserExpect(row.locator('.task-due')).not.toContainText('05:30');
    const deadlineRow = page.locator('.task-row').filter({ hasText: 'Workspace midnight deadline check' });
    await browserExpect(deadlineRow.locator('.task-due')).toContainText('Deadline');
    await browserExpect(deadlineRow.locator('.task-due')).not.toContainText('12:00 am');
    browserExpect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)).toBe('UTC');
    browserExpect(await page.evaluate(() => localStorage.getItem('tantara_token'))).toBeTruthy();
    browserExpect(await page.evaluate(() => document.documentElement.scrollWidth <= 1440)).toBeTruthy();
    await page.screenshot({ path: 'test-results/tasks-workspace-time-proof.png', fullPage: false });
  } finally {
    await request.delete(`${base}/tasks/${(await task.json()).id}`, { headers });
    await request.delete(`${base}/tasks/${(await deadline.json()).id}`, { headers });
  }
});

browserTest(
  'calendar presents midnight deadlines and event records as all day without times',
  async ({ page, request }) => {
    const login = await request.post(`${base}/auth/login`, {
      data: { email: 'advocate@tantara.local', password: 'tantara-local' },
    });
    browserExpect(login.ok()).toBeTruthy();
    const token = (await login.json()).access_token as string;
    const headers = { Authorization: `Bearer ${token}` };
    const day = await page.evaluate(() => {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date());
      const number = (type: string) => Number(parts.find((part) => part.type === type)?.value);
      const target = new Date(Date.UTC(number('year'), number('month') - 1, number('day') + 2));
      return `${target.getUTCFullYear()}-${String(target.getUTCMonth() + 1).padStart(2, '0')}-${String(target.getUTCDate()).padStart(2, '0')}`;
    });
    const created = await request.post(`${base}/cases`, {
      headers,
      data: {
        title: 'UTC calendar all-day proof',
        // Case creation correctly rejects future filing dates. Keep the event
        // under test in the future while the actual filing date is historical.
        filed_at: '2020-01-01T00:00:00+05:30',
      },
    });
    browserExpect(created.ok()).toBeTruthy();
    const caseId = (await created.json()).id as string;
    let eventId: string | undefined;
    let deadlineId: string | undefined;
    try {
      const createdDeadline = await request.post(`${base}/tasks`, {
        headers,
        data: {
          title: 'All-day deadline proof',
          case_id: caseId,
          due_at: `${day}T00:00:00+05:30`,
        },
      });
      browserExpect(createdDeadline.ok()).toBeTruthy();
      deadlineId = (await createdDeadline.json()).id as string;
      const createdEvent = await request.post(`${base}/cases/${caseId}/events`, {
        headers,
        data: { type: 'event', occurred_at: `${day}T00:00:00+05:30`, detail: 'All-day event proof' },
      });
      browserExpect(createdEvent.ok()).toBeTruthy();
      eventId = (await createdEvent.json()).id as string;
      await page.addInitScript((value) => {
        localStorage.setItem('tantara_token', value);
        document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
      }, token);
      await page.goto('/calendar');
      const event = page.getByRole('button', { name: /View All day.*UTC calendar all-day proof/ }).first();
      const deadline = page.getByRole('button', {
        name: /View Deadline.*All-day deadline proof.*UTC calendar all-day proof/,
      });
      await browserExpect(event).toBeVisible();
      await browserExpect(deadline).toBeVisible();
      await browserExpect(event.locator('time')).toHaveCount(0);
      await browserExpect(deadline.locator('time')).toHaveCount(0);
      await event.click();
      const details = page.getByRole('dialog', { name: 'Event details' });
      await browserExpect(details).toContainText('UTC calendar all-day proof');
      await browserExpect(details).toContainText('All day');
      await browserExpect(details).toContainText('All-day event proof');
      browserExpect(await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)).toBe('UTC');
      browserExpect(await page.evaluate(() => localStorage.getItem('tantara_token'))).toBeTruthy();
      browserExpect(await page.evaluate(() => document.documentElement.scrollWidth <= 1440)).toBeTruthy();
      await page.screenshot({ path: 'test-results/calendar-all-day-proof.png', fullPage: false });
    } finally {
      if (deadlineId) await request.delete(`${base}/tasks/${deadlineId}`, { headers });
      if (eventId) await request.delete(`${base}/cases/${caseId}/events/${eventId}`, { headers });
      await request.delete(`${base}/cases/${caseId}`, { headers });
    }
  },
);

browserTest('shell renders the identity returned by the signed-in account', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  browserExpect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/cases');
  await browserExpect(page.locator('.user-caption')).toBeVisible();
});

browserTest(
  'case API projects the earliest future hearing and the list renders it',
  async ({ page, request }) => {
    const login = await request.post(`${base}/auth/login`, {
      data: {
        email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
        password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
      },
    });
    browserExpect(login.ok()).toBeTruthy();
    const token = (await login.json()).access_token;
    const headers = { Authorization: `Bearer ${token}` };
    const casesResponse = await request.get(`${base}/cases?page=1&page_size=100`, { headers });
    const hearingsResponse = await request.get(`${base}/hearings?page=1&page_size=100&sort=at`, { headers });
    browserExpect(casesResponse.ok()).toBeTruthy();
    browserExpect(hearingsResponse.ok()).toBeTruthy();
    const caseRows = (await casesResponse.json()).items as Array<{
      id: string;
      title: string;
      next_hearing_at?: string;
    }>;
    const hearings = (await hearingsResponse.json()).items as Array<{
      case_id?: string;
      at: string;
      title?: string;
    }>;
    browserExpect(hearings.length).toBeGreaterThan(0);
    const linkedCase = caseRows.find(
      (row) => row.next_hearing_at && new Date(row.next_hearing_at).getTime() > Date.now() + 3 * 86400000,
    );
    browserExpect(
      linkedCase,
      'seeded API should have a future hearing far enough ahead to appear in the next calendar month',
    ).toBeTruthy();
    const futureHearings = hearings
      .filter((item) => item.case_id === linkedCase!.id && new Date(item.at) >= new Date())
      .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
    const hearing = futureHearings[0];
    browserExpect(futureHearings.length).toBeGreaterThan(0);
    browserExpect(linkedCase!.next_hearing_at).toBe(hearing.at);
    for (const item of caseRows) {
      if (item.next_hearing_at)
        browserExpect(new Date(item.next_hearing_at).getTime()).toBeGreaterThanOrEqual(Date.now() - 60_000);
    }
    await page.addInitScript((value) => {
      localStorage.setItem('tantara_token', value as string);
      document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
    }, token);
    await page.goto('/cases');
    const row = page.getByRole('row').filter({ has: page.getByRole('link', { name: linkedCase!.title }) });
    await browserExpect(row).toContainText(
      new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(new Date(hearing.at)),
    );
    await page.goto(`/cases/${linkedCase!.id}`);
    await browserExpect(page.locator('.data-list')).toContainText(
      new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(new Date(linkedCase!.next_hearing_at!)),
    );
    await page.goto('/calendar');
    await page.getByRole('button', { name: 'Next period' }).click();
    const selectedLabel = hearing.title || 'Future case conference';
    const eventButton = page
      .getByRole('button', {
        name: new RegExp(`View ${selectedLabel}`, 'i'),
      })
      .first();
    await browserExpect(eventButton).toBeVisible();
    await eventButton.click();
    const eventDetails = page.getByRole('dialog', { name: 'Event details' });
    await browserExpect(eventDetails).toContainText(linkedCase!.title);
    await browserExpect(eventDetails).toContainText(
      new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(new Date(linkedCase!.next_hearing_at!)),
    );
  },
);

browserTest('client case count zero is displayed as a real zero', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  browserExpect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  const response = await request.get(`${base}/clients?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  browserExpect(response.ok()).toBeTruthy();
  const clients = (await response.json()).items as Array<{
    id: string;
    name: string;
    case_count?: number;
  }>;
  const zero = clients.find((client) => client.case_count === 0);
  browserExpect(zero, 'seed includes a client whose real case_count is zero').toBeTruthy();
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);
  await page.goto('/clients');
  const row = page.getByRole('row').filter({ hasText: zero!.name });
  await browserExpect(row.locator('td').nth(2)).toHaveText('0');
});

browserTest('client directory keeps every API row visible in mobile cards', async ({ page, request }) => {
  const login = await request.post(`${base}/auth/login`, {
    data: {
      email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
      password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
    },
  });
  browserExpect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token;
  await page.addInitScript((value) => {
    localStorage.setItem('tantara_token', value as string);
    document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
  }, token);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/clients');
  const desktopRows = page.locator('.matter-table tbody tr');
  await browserExpect(desktopRows).toHaveCount(7);
  const rowCount = await desktopRows.count();

  await page.setViewportSize({ width: 390, height: 844 });
  const cards = page.locator('.matter-mobile-cards[aria-label="Clients"] .matter-mobile-case');
  await browserExpect(cards).toHaveCount(rowCount);
  await browserExpect(cards.first()).toBeVisible();
  for (let index = 0; index < rowCount; index += 1) await browserExpect(cards.nth(index)).toBeVisible();
  await browserExpect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

browserTest(
  'calendar labels real event records as all day without a time or raw event enums',
  async ({ page, request }) => {
    const login = await request.post(`${base}/auth/login`, {
      data: {
        email: process.env.TANTARA_E2E_EMAIL || 'advocate@tantara.local',
        password: process.env.TANTARA_E2E_PASSWORD || 'tantara-local',
      },
    });
    const token = (await login.json()).access_token;
    const headers = { Authorization: `Bearer ${token}` };
    const parts = await page.evaluate(() => {
      const values = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date());
      const number = (type: string) => Number(values.find((part) => part.type === type)?.value);
      const date = new Date(Date.UTC(number('year'), number('month') - 1, number('day') + 2));
      return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
    });
    const createdCase = await request.post(`${base}/cases`, {
      headers,
      data: { title: `All-day event check ${Date.now()}` },
    });
    browserExpect(createdCase.ok()).toBeTruthy();
    const caseId = (await createdCase.json()).id as string;
    let eventId: string | undefined;
    try {
      const createdEvent = await request.post(`${base}/cases/${caseId}/events`, {
        headers,
        data: { type: 'event', occurred_at: `${parts}T00:00:00+05:30`, detail: 'All-day event test record' },
      });
      browserExpect(createdEvent.ok()).toBeTruthy();
      eventId = (await createdEvent.json()).id as string;
      await page.addInitScript((value) => {
        localStorage.setItem('tantara_token', value as string);
        document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
      }, token);
      const calendarResponse = page.waitForResponse(
        (response) => new URL(response.url()).pathname === '/api/v1/calendar' && response.status() === 200,
      );
      await page.goto('/calendar');
      const calendarPayload = await (await calendarResponse).json();
      const calendarItems = Array.isArray(calendarPayload) ? calendarPayload : calendarPayload.items;
      browserExpect(
        calendarItems.some((item: { id: string }) => item.id === eventId),
        `calendar API should contain created event ${eventId} for ${parts}`,
      ).toBeTruthy();
      const allDayEvent = page.getByRole('button', {
        name: /View All day.*All-day event check/,
      });
      await browserExpect(allDayEvent).toBeVisible({ timeout: 15_000 });
      await browserExpect(allDayEvent.locator('time')).toHaveCount(0);
      await browserExpect(allDayEvent).toContainText('All-day event test record');
      await browserExpect(allDayEvent).toContainText(`All-day event check`);
      const eventLabels = await page
        .locator('.calendar-event')
        .evaluateAll((buttons) => buttons.map((button) => button.getAttribute('aria-label') || ''));
      browserExpect(new Set(eventLabels).size).toBe(eventLabels.length);
      await allDayEvent.click();
      const details = page.getByRole('dialog', { name: 'Event details' });
      await browserExpect(details).toContainText('All day');
      await browserExpect(details).toContainText('All-day event test record');
      await browserExpect(details).toContainText(`All-day event check`);
      await browserExpect(details).not.toContainText(/\b\d{1,2}:\d{2}\b|\b(am|pm)\b/i);
      await browserExpect(page.locator('body')).not.toContainText(
        /all_day_event|first_hearing|hearing_completed|document_uploaded|deadline_set/i,
      );
    } finally {
      if (eventId) await request.delete(`${base}/cases/${caseId}/events/${eventId}`, { headers });
      await request.delete(`${base}/cases/${caseId}`, { headers });
    }
  },
);
