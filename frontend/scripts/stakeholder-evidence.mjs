// Stakeholder evidence run: replays the six TANTRA test cases and the five
// reported defects against a deployed site and writes screenshots plus a
// machine-readable verdict file for the evidence report.
//
//   cd frontend && node scripts/stakeholder-evidence.mjs \
//       --base https://tantara-prod.web.app --label before-prod
//
// Nothing secret is printed. Accounts it creates use the `qa.<label>.` prefix so
// scripts/prod_db.py prune-probes can remove them afterwards.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const index = argv.indexOf(`--${name}`);
  return index >= 0 ? argv[index + 1] : fallback;
};
const SITE = (arg('base', process.env.TANTARA_SITE_URL ?? 'https://tantara-prod.web.app')).replace(/\/$/, '');
const LABEL = arg('label', `run-${Date.now()}`);
const OUT = path.resolve(import.meta.url.replace('file://', ''), '../../..', 'reports/evidence', LABEL);
fs.mkdirSync(OUT, { recursive: true });

const stamp = Date.now().toString(36);
const password = 'Tantra-Test-2026!';
const results = [];
const consoleErrors = [];

const record = (id, claim, verdict, detail, shot) => {
  results.push({ id, claim, verdict, detail, shot: shot ? path.basename(shot) : null });
  const mark = { pass: 'PASS', fail: 'FAIL', partial: 'PARTIAL', blocked: 'BLOCKED' }[verdict] ?? verdict;
  console.log(`${mark.padEnd(8)} ${id} — ${claim}${detail ? ` :: ${detail}` : ''}`);
};

const has = (text, ...needles) => needles.every((needle) => text.toLowerCase().includes(needle.toLowerCase()));

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log('  shot', name);
  return file;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Cloud Run / Hosting can answer 429 with Google's "Rate exceeded." body; back off and retry.
function writeSummary() {
  // Written even when the run dies part way through, so evidence is never lost.
  if (writeSummary.done) return;
  writeSummary.done = true;
  const summary = {
    site: SITE,
    label: LABEL,
    ranAt: new Date().toISOString(),
    account: account?.email ?? null,
    results,
    consoleErrors: [...new Set(consoleErrors)].slice(0, 40),
  };
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(summary, null, 2));
  console.log(`\nwrote ${path.join(OUT, 'results.json')} (${results.length} checks)`);
}

process.on('uncaughtException', (error) => {
  console.log(`FATAL: ${String(error?.stack ?? error).split('\n').slice(0, 4).join(' | ')}`);
  writeSummary();
  process.exitCode = 1;
});

async function fetchWithRetry(url, options = {}, attempts = 6) {
  // A single network blip must not destroy a 20-minute evidence run: retry, then
  // hand back an empty response so the caller records a failed check instead.
  let lastError = null;
  let response = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      response = await fetch(url, options);
      if (response.status !== 429 && response.status < 500) return response;
    } catch (error) {
      lastError = error;
      console.log(`  network retry ${attempt + 1}/${attempts}: ${String(error?.message ?? error).slice(0, 90)}`);
    }
    await sleep(4000 * (attempt + 1));
  }
  if (lastError) console.log(`  network giving up: ${String(lastError?.message ?? lastError).slice(0, 120)}`);
  if (!response) return { status: 0, ok: false, async text() { return ''; } };
  return response;
}

async function api(token, route, options = {}) {
  const headers = { Authorization: `Bearer ${token}`, ...(options.headers ?? {}) };
  if (options.body !== undefined && !headers['content-type']) headers['content-type'] = 'application/json';
  const response = await fetchWithRetry(`${SITE}/api/v1${route}`, { ...options, headers });
  const text = await response.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = text.slice(0, 400);
  }
  return { status: response.status, body };
}

async function register(name, emailTag, roleTitle = 'Advocate') {
  const email = `qa.${LABEL}.${emailTag}@theessencetimes.com`;
  const created = await fetchWithRetry(`${SITE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, email, password, title: roleTitle }),
  });
  if (!created.ok) throw new Error(`register ${email}: ${created.status} ${(await created.text()).slice(0, 200)}`);
  const data = await created.json();
  return { email, token: data.access_token, user: data.user };
}

async function signIn(page, token) {
  await page.goto(`${SITE}/signin`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ([value]) => {
      localStorage.setItem('tantara_token', value);
      document.cookie = `tantara_token=${value}; Path=/; SameSite=Lax`;
    },
    [token],
  );
}

const CASE = {
  title: 'Zenith Traders vs. Orion Components',
  type: 'Arbitration',
  client: 'Zenith Traders',
  opposing: 'Orion Components',
  institution: 'SIAC',
  law: 'Indian law',
  seat: 'Mumbai, India',
  amount: '1250000',
  status: 'active',
  description: 'Dispute arising from non-payment under a fictional supply agreement',
};

const DOC_TEXT = `FICTIONAL ARBITRATION AGREEMENT

Agreement Reference: TANTRA-TEST-2026-001

Party A: Zenith Traders
Party B: Orion Components

The parties agree that disputes arising from
this fictional agreement shall be referred to
arbitration.

The seat of arbitration shall be Mumbai, India.

The arbitral tribunal shall consist of one
sole arbitrator appointed by mutual agreement.

The language of arbitration shall be English.

The parties shall attempt to resolve disputes
through mutual discussion before commencing
arbitration.

This is fictional test content created solely
for testing the TANTRA platform.
`;

const Q_UPLOAD =
  'What is the agreement reference number in the uploaded arbitration agreement, who are the two parties, what is the seat of arbitration, and how many arbitrators are provided for?';

const Q_SECTION9 = `Under the Arbitration and Conciliation Act, 1996, when can a court grant interim measures in relation to arbitration under Section 9? Explain the position before commencement of arbitration, during arbitration, and after the arbitral tribunal has been constituted. Also explain the relationship between Section 9 and Section 17.`;

const DRAFT_INSTRUCTION = `Prepare a formal legal notice on behalf of Zenith
Traders against Orion Components concerning
non-payment of ₹12,50,000 under a fictional
supply agreement.

Known facts:
1. Zenith Traders supplied goods to Orion Components.
2. The outstanding amount is ₹12,50,000.
3. The parties have an arbitration agreement.
4. The seat of arbitration is Mumbai, India.
5. The agreement provides for a sole arbitrator.

Important missing information:
- Date of agreement.
- Invoice numbers.
- Dates of supply.
- Payment due date.
- Date of default.
- Whether any previous payment demands were issued.
- Whether any payment was received.
- Names and addresses of authorised representatives.

Draft a structured legal notice using only the facts
provided.

Do not invent invoice numbers, dates, addresses,
payment demands, communications or admissions.

Mark every missing fact with a clearly visible
[TO BE CONFIRMED] placeholder.

Identify any additional documents required
before the notice can be finalised.

Include relevant legal provisions only where
supported by the available legal sources.`;

console.log(`site: ${SITE}   label: ${LABEL}   out: ${OUT}`);

const account = await register('Evidence Advocate', `adv.${stamp}`);
console.log(`registered advocate account ${account.email}`);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(`${page.url()} :: ${message.text().slice(0, 200)}`);
});
page.on('response', (response) => {
  if (response.status() >= 400)
    consoleErrors.push(`HTTP ${response.status()} ${response.url().replace(SITE, '')}`);
});

await signIn(page, account.token);

// ---------------------------------------------------------------- dashboard
await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
await shot(page, '00-dashboard');

// --------------------------------------------- defect 1 + test 1: new case
const clientOptionsBefore = await (await api(account.token, '/clients?page_size=100')).body;
await page.goto(`${SITE}/cases/new`, { waitUntil: 'networkidle' });
const clientSelect = page.locator('select').filter({ hasText: 'Select client' }).first();
const clientOptionCount = (await clientSelect.count()) ? await clientSelect.locator('option').count() : 0;
const clientHasCreateOption = (await page.locator('text=/add client|new client|create client/i').count()) > 0;
await shot(page, '01-new-case-form');
record(
  'D1',
  'Claim: no clients can be selected in New Case, the name has to be typed',
  clientOptionCount <= 1 && !clientHasCreateOption ? 'fail' : 'pass',
  `client dropdown options=${clientOptionCount} (only "Select client" when 1), inline create control=${clientHasCreateOption}, existing clients=${
    (clientOptionsBefore?.items ?? []).length
  }`,
  path.join(OUT, '01-new-case-form.png'),
);

// Use the inline control that fixes defect 1: create a client from the form and
// confirm it is associated with the matter being saved.
let clientCreated = false;
let clientNote = '';
try {
  await page.getByRole('button', { name: '＋ Add client' }).click();
  const newClientBox = page.getByRole('textbox', { name: 'New client name' });
  await newClientBox.fill(`${CASE.client} Pvt Ltd`);
  await newClientBox.press('Enter');
  await page.waitForTimeout(2500);
  const selectedClient = await page.getByLabel('Client').inputValue().catch(() => '');
  clientCreated = Boolean(selectedClient);
  clientNote = `client select value=${selectedClient || 'none'}`;
} catch (error) {
  clientNote = `inline create control not usable: ${error.message.split('\n')[0]}`;
}
await shot(page, '01b-client-created-inline');
record(
  'D1b',
  'Claim: a client cannot be created from the New Case form',
  clientCreated ? 'not confirmed' : 'confirmed',
  `${clientNote}; the saved case must carry client_id (checked in T1a detail below)`,
  path.join(OUT, '01b-client-created-inline.png'),
);

await page.getByLabel(/case title/i).fill(CASE.title);
const fill = async (label, value) => {
  const field = page.getByLabel(new RegExp(label, 'i')).first();
  if (await field.count()) await field.fill(value);
};
await fill('claimant', CASE.client);
await fill('respondent', CASE.opposing);
const forumSelect = page.locator('select').filter({ hasText: 'Select institution' }).first();
if (await forumSelect.count()) await forumSelect.selectOption({ label: CASE.institution }).catch(() => {});
await fill('seat', CASE.seat);
await fill('governing law', CASE.law);
await fill('dispute category', CASE.type);
await fill('claim amount', CASE.amount);
const statusSelect = page.locator('select').filter({ hasText: 'Active' }).last();
if (await statusSelect.count()) await statusSelect.selectOption({ value: CASE.status }).catch(() => {});
await fill('description', CASE.description);
await shot(page, '02-new-case-filled');
await page.getByRole('button', { name: /save case/i }).click();
await page.waitForURL(/\/cases\/[0-9a-f-]{8}/, { timeout: 20000 }).catch(() => {});
await page.waitForLoadState('networkidle');
const caseUrl = page.url();
const caseId = caseUrl.split('/').pop();
const caseRecord = caseId?.length > 8 ? await api(account.token, `/cases/${caseId}`) : { status: 0, body: {} };
const clientAttached = Boolean(caseRecord.body?.client_id);
record(
  'T1a',
  'Claim: matter is created and opens with the entered details',
  caseId?.length > 8 && clientAttached ? 'pass' : 'fail',
  `navigated to ${caseUrl}; client attached: ${clientAttached ? 'yes' : 'no'}`,
);
await shot(page, '03-case-detail');
const caseBody = await page.locator('main').innerText();
const caseFields = ['Zenith Traders', 'Orion Components', 'SIAC', 'Mumbai', 'Indian law'].filter((needle) =>
  caseBody.includes(needle),
);
record(
  'T1b',
  'Claim: opening the matter shows parties, institution, amount and other details',
  caseFields.length >= 4 ? 'pass' : caseFields.length ? 'partial' : 'fail',
  `visible on detail page: ${caseFields.join(', ') || 'none'}; amount rendered: ${
    /12,50,000|1250000|1,250,000/i.test(caseBody)
  }`,
);

await page.goto(`${SITE}/cases`, { waitUntil: 'networkidle' });
const listText = await page.locator('main').innerText();
record(
  'T1c',
  'Claim: matter appears in My Cases',
  listText.includes(CASE.title) ? 'pass' : 'fail',
  '',
  await shot(page, '04-cases-list'),
);

// --------------------------------------------------- test 1: task + calendar
await page.goto(`${SITE}/tasks`, { waitUntil: 'networkidle' });
await shot(page, '05-tasks-empty');
const newTask = page.getByRole('button', { name: /new task/i }).first();
let taskCreated = false;
if (await newTask.count()) {
  await newTask.click();
  await page.waitForTimeout(600);
  const title = page.getByLabel(/title/i).first();
  if (await title.count()) await title.fill('Review arbitration agreement');
  const due = page.locator('input[type="date"], input[type="datetime-local"]').first();
  if (await due.count()) await due.fill('2026-11-05T09:00');
  const priority = page.locator('select').filter({ hasText: /medium|normal/i }).first();
  if (await priority.count()) await priority.selectOption({ index: 1 }).catch(() => {});
  const matter = page.locator('select').filter({ hasText: /matter|case/i }).last();
  if (await matter.count()) await matter.selectOption({ label: CASE.title }).catch(() => {});
  await shot(page, '06-task-dialog');
  await page.getByRole('button', { name: /(save|create|add) task|^(save|create)$/i }).last().click();
  await page.waitForTimeout(2500);
  taskCreated = true;
}
await page.reload({ waitUntil: 'networkidle' });
const tasksText = await page.locator('main').innerText();
record(
  'T1d',
  'Claim: task is created, linked to the matter and survives a refresh',
  tasksText.includes('Review arbitration agreement') ? 'pass' : 'fail',
  `task dialog used=${taskCreated}`,
  await shot(page, '07-tasks-after-reload'),
);
const taskApi = await api(account.token, '/tasks?page_size=50');
const taskRows = Array.isArray(taskApi.body) ? taskApi.body : (taskApi.body?.items ?? []);
const taskItem = taskRows.find((item) => item.title === 'Review arbitration agreement');

await page.goto(`${SITE}/calendar`, { waitUntil: 'networkidle' });
await shot(page, '08-calendar-current-month');
const calendarText = await page.locator('main').innerText();
// walk to November 2026 looking for the task
let calendarHit = false;
for (let step = 0; step < 14 && !calendarHit; step += 1) {
  if (calendarText.includes('Review arbitration agreement')) break;
  const next = page.getByRole('button', { name: /next/i }).first();
  if (!(await next.count())) break;
  await next.click();
  await page.waitForTimeout(900);
  calendarHit = (await page.locator('main').innerText()).includes('Review arbitration agreement');
}
if (!calendarHit) calendarHit = calendarText.includes('Review arbitration agreement');
record(
  'T1e',
  'Claim: calendar displays the task due date',
  calendarHit ? 'pass' : 'fail',
  `task due_at from API=${taskItem?.due_at ?? 'none'}`,
  await shot(page, '09-calendar-november-2026'),
);

// ----------------------------------------- test 2 + defect 3: upload pipeline
const docFile = path.join(OUT, 'TANTRA-TEST-ARBITRATION.txt');
const uniqueText = `${DOC_TEXT}\nRun identifier: ${stamp}\n`;
fs.writeFileSync(docFile, uniqueText);
await page.goto(`${SITE}/documents`, { waitUntil: 'networkidle' });
await page.setInputFiles('input[type="file"]', docFile);
await page.waitForTimeout(4000);
await shot(page, '10-upload-queue-processing');
const startedAt = Date.now();
let finalStatus = 'unknown';
let docId = null;
const queueSamples = [];
while (Date.now() - startedAt < 300000) {
  const queueText = (await page.locator('.documents-queue').innerText().catch(() => '')).replace(/\s+/g, ' ');
  const list = await api(account.token, '/documents?page_size=100');
  const mine = (list.body?.items ?? []).find((item) => (item.title ?? '').includes('TANTRA-TEST-ARBITRATION'));
  if (mine) {
    docId = mine.id;
    finalStatus = mine.status;
  }
  queueSamples.push(`${Math.round((Date.now() - startedAt) / 1000)}s queue="${queueText.slice(0, 90)}" api=${finalStatus}`);
  if (['ready', 'failed'].includes(finalStatus)) break;
  await page.waitForTimeout(4000);
}
const seconds = Math.round((Date.now() - startedAt) / 1000);
// Give the interface the same chance a user has: after the server reports a
// terminal status, the row must leave "Processing" on its own within a few seconds.
await page.waitForTimeout(9000);
const queueAtEnd = (await page.locator('.documents-queue').innerText().catch(() => '')).replace(/\s+/g, ' ');
const listAtEnd = await page.locator('main').innerText();
await shot(page, '11-documents-upload-state');
const queueReachedTerminal = /ready|complete|failed|open|retry/i.test(queueAtEnd);
const uiStuckProcessing = /processing/i.test(queueAtEnd) && !queueReachedTerminal && finalStatus === 'ready';
record(
  'D3',
  'Claim: document upload never finishes and stays on Processing',
  finalStatus === 'ready' && !uiStuckProcessing ? 'not confirmed' : 'confirmed',
  `API status=${finalStatus} after ${seconds}s; queue label without reload="${queueAtEnd.slice(0, 120)}"; stuck on Processing=${uiStuckProcessing}; library badge shows Ready=${/ready/i.test(
    listAtEnd,
  )}; samples=${queueSamples.slice(-3).join(' | ')}`.replace('; ;', ';'),
  path.join(OUT, '11-documents-upload-state.png'),
);
record(
  'T2a',
  'Claim: uploaded document appears in the library and reaches Ready',
  finalStatus === 'ready' ? 'pass' : 'fail',
  `status=${finalStatus}, seconds=${seconds}, document_id=${docId ?? 'none'}`,
);

// Optional realistic upload: a multi-page statute PDF, watched in the queue with no reload.
let pdfDocId = null;
if (process.env.PROBE_PDF) {
  const pdfPath = process.env.PROBE_PDF;
  await page.goto(`${SITE}/documents`, { waitUntil: 'networkidle' });
  await page.setInputFiles('input[type="file"]', pdfPath);
  const pdfStart = Date.now();
  let pdfStatus = 'unknown';
  const pdfSamples = [];
  while (Date.now() - pdfStart < 420000) {
    const q = (await page.locator('.documents-queue').innerText().catch(() => '')).replace(/\s+/g, ' ');
    const list = await api(account.token, '/documents?page_size=100');
    const mine = (list.body?.items ?? []).find((item) => (item.filename ?? item.title ?? '').startsWith('Specific Relief'));
    if (mine) {
      pdfStatus = mine.status;
      pdfDocId = mine.id;
    }
    pdfSamples.push(`${Math.round((Date.now() - pdfStart) / 1000)}s api=${pdfStatus} queue="${q.slice(0, 80)}"`);
    if (['ready', 'failed'].includes(pdfStatus)) break;
    await page.waitForTimeout(5000);
  }
  await shot(page, '11b-pdf-upload-state');
  record(
    'T2d',
    'A 17-page statute PDF uploads, indexes and leaves the queue without a page reload',
    pdfStatus === 'ready' && /ready|open/i.test(pdfSamples.at(-1) ?? '') ? 'pass' : 'partial',
    `status=${pdfStatus} after ${Math.round((Date.now() - pdfStart) / 1000)}s; last samples=${pdfSamples.slice(-2).join(' | ')}`,
    path.join(OUT, '11b-pdf-upload-state.png'),
  );
}

// ------------------------------------------------- test 2 + defect 4: search
await page.goto(`${SITE}/search`, { waitUntil: 'networkidle' });
const searchBox = page.locator('input[type="search"], input[name="query"], input[placeholder*="earch" i]').first();
await searchBox.fill('TANTRA-TEST-2026-001');
await searchBox.press('Enter');
await page.waitForTimeout(6000);
const searchShot = await shot(page, '12-search-reference');
const searchBody = await page.locator('main').innerText();
const searchApi = await api(account.token, '/search/documents?query=TANTRA-TEST-2026-001&page=1&page_size=10');
const searchHits = (searchApi.body?.items ?? []).length;
const withSnippet = (searchApi.body?.items ?? []).filter((item) => (item.snippet || '').length > 40).length;
record(
  'D4',
  'Claim: search does not fetch the document information',
  searchHits > 0 && withSnippet > 0 ? 'not confirmed' : 'confirmed',
  `API hits=${searchHits}, hits with readable snippet=${withSnippet}; UI mentions reference: ${searchBody.includes(
    'TANTRA-TEST-2026-001',
  )}`,
  searchShot,
);
await searchBox.fill('sole arbitrator Mumbai seat');
await searchBox.press('Enter');
await page.waitForTimeout(6000);
await shot(page, '13-search-seat');

// Associate the agreement with the matter: the draft builder draws its evidence
// from documents linked to the case, exactly as an advocate would.
if (docId) await api(account.token, `/documents/${docId}`, { method: 'PATCH', body: JSON.stringify({ case_id: caseId }) });

// ------------------------------------------ test 2 + defect 5: AI read panel
const docDetail = await api(account.token, '/documents?page_size=100');
const testDoc = (docDetail.body?.items ?? []).find((item) => (item.title ?? '').includes('TANTRA-TEST-ARBITRATION'));
if (testDoc) {
  await page.goto(`${SITE}/documents/${testDoc.id}`, { waitUntil: 'networkidle' });
  await shot(page, '14-document-detail');
  await page.evaluate(() => document.querySelectorAll('details').forEach((n) => (n.open = true)));
  await page.waitForTimeout(1200);
  const extractedText = await page.locator('main').innerText();
  await shot(page, '14b-document-detail-expanded');
  record(
    'T2b',
    'Claim: extracted text of the uploaded document is readable',
    extractedText.includes('TANTRA-TEST-2026-001') ? 'pass' : 'fail',
    `detail page shows agreement reference: ${extractedText.includes('TANTRA-TEST-2026-001')}`,
  );
  const aiStatusApi = await api(account.token, '/ai/status');
  const aiState = aiStatusApi.body?.llm ?? aiStatusApi.body?.ai ?? {};
  const aiButton = page.getByRole('button', { name: /run extraction|ai read|ai extract|extract/i }).first();
  if (await aiButton.count()) {
    const panel = page
      .locator('section, aside, .card, .panel')
      .filter({ hasText: /Document extraction/i })
      .first();
    const before = (await panel.innerText().catch(() => '')).replace(/\s+/g, ' ');
    await aiButton.click();
    let after = before;
    // Wait for the extraction to reach a terminal state before judging the panel.
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await page.waitForTimeout(3000);
      after = (await panel.innerText().catch(() => '')).replace(/\s+/g, ' ');
      if (attempt > 0 && !/extracting|processing|running/i.test(after)) break;
    }
    const aiRead = await api(account.token, `/documents/${docId}/ai`).catch(() => null);
    const readState = aiRead?.body ?? {};
    const partiesShown = /zenith/i.test(after) && /orion/i.test(after);
    const notExtracted = (after.match(/not extracted/gi) ?? []).length;
    const namesClaude = /claude|anthropic/i.test(after);
    const claimsLocalOnly = /local text extraction/i.test(after) && !namesClaude;
    const labelIndex = after.toLowerCase().indexOf('configured model');
    const modelLabel = labelIndex >= 0 ? after.slice(labelIndex, labelIndex + 70) : 'n/a';
    record(
      'D5',
      'Claim: AI extraction in the Documents section is not working',
      partiesShown && !claimsLocalOnly ? 'not confirmed' : 'confirmed',
      `panel parties=${partiesShown}, "Not extracted" fields=${notExtracted}, names the configured model=${namesClaude}, model label="${modelLabel}", ai/status provider=${aiState.provider ?? 'n/a'} model=${aiState.model ?? 'n/a'} reachable=${aiState.reachable ?? 'n/a'}, ai read status=${readState.status ?? 'n/a'} model=${readState.model ?? 'n/a'} source=${readState.source ?? 'n/a'}`,
      await shot(page, '15-ai-read-panel'),
    );
    record(
      'AI1',
      'AI service reports its real provider, model and reachability',
      /claude|anthropic/i.test(String(aiState.model ?? '')) ? 'pass' : 'fail',
      JSON.stringify({ provider: aiState.provider, model: aiState.model, reachable: aiState.reachable, base_url: aiState.base_url }),
    );
  } else {
    record('D5', 'Claim: AI extraction in the Documents section is not working', 'blocked', 'no AI-read control found', await shot(page, '15-ai-read-missing'));
  }
}

// ------------------------------------------------- test 3: research accuracy
await page.goto(`${SITE}/research`, { waitUntil: 'networkidle' });
const questionBox = page.locator('textarea').first();
await questionBox.fill(Q_SECTION9);
await page.getByRole('button', { name: /^ask|ask tanya|ask tantra|send/i }).last().click();
await page.waitForTimeout(45000);
const researchShot = await shot(page, '16-research-section-9');
const researchBody = await page.locator('main').innerText();
const sectionPoints = {
  'section 9 mentioned': /section 9|section9|s\.?9\b/i.test(researchBody),
  'section 17 mentioned': /section 17/i.test(researchBody),
  'post-constitution restriction': /tribunal (?:is |has been |)constituted|after (?:the )?(?:arbitral )?tribunal|ordinarily (?:should |will )?not/i.test(
    researchBody,
  ),
  'model generated answer': !/model unavailable|evidence only/i.test(researchBody),
};
record(
  'T3a',
  'Claim: research desk explains Sections 9 and 17 with citations',
  Object.values(sectionPoints).every(Boolean) ? 'pass' : 'partial',
  JSON.stringify(sectionPoints),
  researchShot,
);
const citationChips = await page.locator('a[href*="/documents/"], button:has-text("p.")').count();
record('T3b', 'Citation chips link to the cited document page', citationChips > 0 ? 'pass' : 'fail', `chips=${citationChips}`);
// The answer must be generated prose over the cited excerpts, not a quote dump.
const sectionAsk = await api(account.token, '/ai/ask', { method: 'POST', body: JSON.stringify({ question: Q_SECTION9, top_k: 8 }) });
const askChecks = {
  answer_kind: sectionAsk.body?.answer_kind ?? 'n/a',
  model: sectionAsk.body?.model?.model ?? 'n/a',
  citations: (sectionAsk.body?.citations ?? []).length,
  answer_chars: (sectionAsk.body?.answer ?? '').length,
  quote_dump: /^“/.test((sectionAsk.body?.answer ?? '').trim()),
};
record(
  'T3c',
  'The desk synthesises an answer in prose over the cited sources',
  askChecks.answer_kind === 'model_synthesis' && !askChecks.quote_dump && askChecks.citations > 0 ? 'pass' : 'fail',
  JSON.stringify(askChecks),
);

// ------------------------------------------- test 2 answer quality via desk
// Scope the desk to the matter the agreement was uploaded to, and start a clean
// conversation so the answer judged here is only the answer to this question.
await page.goto(`${SITE}/research`, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: /new research/i }).first().click().catch(() => {});
await page.waitForTimeout(2500);
const caseScope = page.getByLabel('Case');
if (await caseScope.count()) await caseScope.selectOption({ index: 1 }).catch(() => {});
await page.waitForTimeout(1500);
const secondBox = page.locator('textarea').first();
await secondBox.fill(Q_UPLOAD);
await page.getByRole('button', { name: /^ask|send/i }).last().click();
let uploadAnswerBody = '';
let previousAnswer = '';
for (let attempt = 0; attempt < 40; attempt += 1) {
  await page.waitForTimeout(3000);
  uploadAnswerBody = await page.locator('main').innerText();
  if (attempt > 2 && uploadAnswerBody === previousAnswer && uploadAnswerBody.length > 400) break;
  previousAnswer = uploadAnswerBody;
}
await shot(page, '17-research-uploaded-agreement');
const answers = {
  reference: uploadAnswerBody.includes('TANTRA-TEST-2026-001'),
  partyA: /zenith/i.test(uploadAnswerBody),
  partyB: /orion/i.test(uploadAnswerBody),
  seat: /mumbai/i.test(uploadAnswerBody),
  soleArbitrator: /sole|one arbitrator|1 arbitrator/i.test(uploadAnswerBody),
};
record(
  'T2c',
  'Claim: research desk answers all five questions about the uploaded agreement',
  Object.values(answers).every(Boolean) ? 'pass' : 'fail',
  JSON.stringify(answers),
  path.join(OUT, '17-research-uploaded-agreement.png'),
);

// ------------------------------------------------------------- test 4: draft
await page.goto(`${SITE}/drafts`, { waitUntil: 'networkidle' });
await shot(page, '18-drafts-list');
const matterPick = page.locator('select').filter({ hasText: /select|matter|case/i }).first();
if (await matterPick.count()) await matterPick.selectOption({ index: 1 }).catch(() => {});
// Test 4 asks for a legal notice, so choose that document type rather than the default claim.
await page.getByRole('button', { name: /notice invoking arbitration/i }).first().click().catch(() => {});
const templatePick = page.locator('select').filter({ hasText: /template|type|notice|statement/i }).nth(1);
if (await templatePick.count()) await templatePick.selectOption({ index: 1 }).catch(() => {});
// The builder only drafts from documents the advocate ticks as supporting sources.
let sourcesTicked = 0;
const sourcesPanel = page.locator('details').filter({ hasText: /case documents/i }).first();
if (await sourcesPanel.count()) {
  await sourcesPanel.locator('summary').click().catch(() => {});
  await page.waitForTimeout(1500);
  const boxes = sourcesPanel.locator('input[type="checkbox"]');
  sourcesTicked = await boxes.count();
  for (let index = 0; index < sourcesTicked; index += 1) await boxes.nth(index).check().catch(() => {});
}
const instructionBox = page.locator('textarea.draft-textarea, textarea').first();
if (await instructionBox.count()) await instructionBox.fill(DRAFT_INSTRUCTION);
await shot(page, '19-draft-builder');
const generateButton = page.locator('button.draft-primary, button:has-text("Generate")').last();
await generateButton.click();
await page.waitForTimeout(90000);
const draftBody = await page.locator('main').innerText();
await shot(page, '20-draft-generated');
const draftChecks = {
  placeholders: (draftBody.match(/TO BE CONFIRMED/gi) ?? []).length,
  mentionsAmount: /12,50,000|1,250,000|1250000/.test(draftBody),
  citesSources: /section|arbitration and conciliation/i.test(draftBody),
  length: draftBody.length,
  modelUnavailableNotice: /model (?:is )?unavailable|evidence only/i.test(draftBody),
  caseDocumentsOffered: sourcesTicked,
};
record(
  'T4',
  'Claim: draft builder produces a usable, cited draft with marked missing facts',
  draftChecks.placeholders > 3 && draftChecks.mentionsAmount && !draftChecks.modelUnavailableNotice
    ? 'pass'
    : 'fail',
  JSON.stringify(draftChecks),
  path.join(OUT, '20-draft-generated.png'),
);

// ----------------------------------------------------------- test 5: bundle
await page.goto(`${SITE}/bundles`, { waitUntil: 'networkidle' });
const createToggle = page.locator('button.bundle-primary').first();
if (await createToggle.count()) await createToggle.click();
const bundleNameField = page.getByLabel(/name|title/i).first();
if (await bundleNameField.count()) await bundleNameField.fill('Zenith Traders – Arbitration Paperbook – Test 01');
const bundleCaseSelect = page.locator('select').first();
if (await bundleCaseSelect.count()) await bundleCaseSelect.selectOption({ index: 1 }).catch(() => {});
await shot(page, '21-bundle-form');
const bundleApi = await api(account.token, '/bundles', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    name: 'Zenith Traders – Arbitration Paperbook – Test 01',
    case_id: caseId,
    settings: { cover_page: true, index: true, synopsis: true, list_of_dates: true },
  }),
});
const bundleId = bundleApi.body?.id;
// Bundle only documents this account owns: the uploaded agreement and the statute PDF.
const docsForBundle = [docId, pdfDocId].filter(Boolean);
if (bundleId) {
  // Items are replaced as a whole array: PUT /bundles/{id}/items {items:[…]}.
  await api(account.token, `/bundles/${bundleId}/items`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      items: docsForBundle.map((documentId, index) => ({
        document_id: documentId,
        section: 'Pleadings & Documents',
        order: index,
      })),
    }),
  });
  await page.goto(`${SITE}/bundles/${bundleId}`, { waitUntil: 'networkidle' });
  await shot(page, '22-bundle-items');
  const generateBundle = page.locator('button:has-text("Generate Bundle")').first();
  const generateEnabled = (await generateBundle.count()) && !(await generateBundle.isDisabled());
  if (generateEnabled) await generateBundle.click();
  else await api(account.token, `/bundles/${bundleId}/generate`, { method: 'POST' });
  let generated = 'unknown';
  for (let attempt = 0; attempt < 24; attempt += 1) {
    const check = await api(account.token, `/bundles/${bundleId}`);
    generated = check.body?.status ?? 'unknown';
    if (['ready', 'complete', 'failed'].includes(generated)) break;
    await page.waitForTimeout(5000);
  }
  await page.reload({ waitUntil: 'networkidle' });
  const previewPages = await page.locator('[data-testid="pdf-page-count"]').innerText().catch(() => 'n/a');
  await shot(page, '22-bundle-detail');
  let downloadedBytes = 0;
  let looksPdf = false;
  try {
    const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
    await page.locator('button:has-text("Download PDF")').first().click();
    const download = await downloadPromise;
    const saved = path.join(OUT, 'bundle-download.pdf');
    await download.saveAs(saved);
    const head = fs.readFileSync(saved).subarray(0, 5).toString();
    downloadedBytes = fs.statSync(saved).size;
    looksPdf = head === '%PDF-';
  } catch {
    const direct = await fetchWithRetry(`${SITE}/api/v1/bundles/${bundleId}/download`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const buffer = Buffer.from(await direct.arrayBuffer());
    fs.writeFileSync(path.join(OUT, 'bundle-download.pdf'), buffer);
    downloadedBytes = buffer.length;
    looksPdf = buffer.subarray(0, 5).toString() === '%PDF-';
  }
  record(
    'T5',
    'Claim: bundle merges the selected documents into a downloadable PDF',
    ['ready', 'complete'].includes(generated) && looksPdf ? 'pass' : 'fail',
    `generate=${generated}, pdf magic=${looksPdf}, bytes=${downloadedBytes}, viewer page count=${previewPages}, documents added=${docsForBundle.length}`,
    path.join(OUT, '22-bundle-detail.png'),
  );
} else {
  record(
    'T5',
    'Claim: bundle merges the selected documents into a downloadable PDF',
    'fail',
    `bundle create failed: ${bundleApi.status} ${JSON.stringify(bundleApi.body).slice(0, 160)}`,
    path.join(OUT, '21-bundle-form.png'),
  );
}

// ------------------------------------------- every workspace page must load
const crawlRoutes = [
  '/dashboard',
  '/cases',
  '/clients',
  '/tasks',
  '/calendar',
  '/documents',
  '/search',
  '/research',
  '/drafts',
  '/autofill',
  '/bundles',
  '/strategy',
  '/community',
  '/settings/profile',
];
for (const route of crawlRoutes) {
  const errorsBefore = consoleErrors.length;
  let main = '';
  let note = '';
  try {
    await page.goto(`${SITE}${route}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    main = await page.locator('main').innerText().catch(() => '');
  } catch (error) {
    note = `navigation error: ${error.message.split('\n')[0]}`;
  }
  const newErrors = consoleErrors.length - errorsBefore;
  const slug = route.replaceAll('/', '-');
  record(
    `C-${slug}`,
    `The ${route} page loads with real content and without script errors`,
    newErrors === 0 && main.length > 60 ? 'pass' : 'fail',
    `${note}main chars=${main.length}, new console errors=${newErrors}`,
    await shot(page, `26-page${slug}`),
  );
}

// ------------------------------------------- defect 2: nav icons and controls
const iconChecks = [
  ['calendar', async () => {
    await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await page.locator('nav a', { hasText: /calendar/i }).first().click();
  }],
  ['settings', async () => {
    await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await page.locator('nav a', { hasText: /settings/i }).first().click();
  }],
  ['activity-bell', async () => {
    await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await page.locator('header button[aria-label="Recent activity"]').click();
  }],
  ['account-menu', async () => {
    await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await page.locator('header button[aria-label="Account menu"]').click();
  }],
  ['global-search', async () => {
    await page.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await page.locator('header button[aria-label="Site search"]').click();
    await page.keyboard.type('arbitration');
  }],
  ['task-complete-toggle', async () => {
    await page.goto(`${SITE}/tasks`, { waitUntil: 'networkidle' });
    const toggle = page.locator('input[type="checkbox"], button[aria-label*="omplete" i]').first();
    if (await toggle.count()) await toggle.click();
  }],
];
for (const [index, [name, action]] of iconChecks.entries()) {
  let detail = '';
  let ok = false;
  try {
    await action();
    await page.waitForTimeout(2500);
    const body = await page.locator('body').innerText();
    const main = await page.locator('main').innerText().catch(() => '');
    const popover = await page.locator('.notification-pop, .profile-pop, .dialog').count();
    ok = main.length > 60 || popover > 0;
    detail = `landed=${page.url().replace(SITE, '')}, main chars=${main.length}, popover=${popover}, body has content=${body.length > 200}`;
  } catch (error) {
    detail = `error: ${error.message.split('\n')[0]}`;
  }
  const file = await shot(page, `23-icon-${index + 1}-${name}`);
  record(
    `D2-${index + 1}`,
    `Claim: the ${name.replace(/-/g, ' ')} control does not work`,
    ok ? 'not confirmed' : 'confirmed',
    detail,
    file,
  );
}

// ----------------------------------------------------- test 6: isolation
const second = await register('Evidence Associate', `assoc.${stamp}`);
const contextB = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const pageB = await contextB.newPage();
await signIn(pageB, second.token);
await pageB.goto(`${SITE}/cases`, { waitUntil: 'networkidle' });
const otherCases = await pageB.locator('main').innerText();
const searchLeak = await api(second.token, `/search/documents?query=${encodeURIComponent(CASE.title)}`);
const caseLeak = await api(second.token, `/cases?q=${encodeURIComponent(CASE.title)}`);
await shot(pageB, '24-isolation-cases');
record(
  'T6a',
  'Claim: another advocate cannot see a colleague’s matters',
  !otherCases.includes(CASE.title) && (caseLeak.body?.items ?? []).length === 0 ? 'pass' : 'fail',
  `case rows leaked in list=${otherCases.includes(CASE.title)}, /cases?q= hits=${(caseLeak.body?.items ?? []).length}, document search hits=${(searchLeak.body?.items ?? []).length}`,
  path.join(OUT, '24-isolation-cases.png'),
);
const roleAttempt = await fetch(`${SITE}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    name: 'Evidence Researcher',
    email: `qa.${LABEL}.res.${stamp}@theessencetimes.com`,
    password,
    title: 'Researcher',
    role: 'researcher',
  }),
});
const roleBody = roleAttempt.ok ? await roleAttempt.json() : {};
const seededResearcher = process.env.RESEARCHER_EMAIL && process.env.RESEARCHER_PASSWORD;
if (seededResearcher) {
  const login = await fetchWithRetry(`${SITE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: process.env.RESEARCHER_EMAIL, password: process.env.RESEARCHER_PASSWORD }),
  });
  const loginBody = login.ok ? await login.json() : {};
  const roleToken = loginBody.access_token;
  if (roleToken) {
    const form = new FormData();
    form.append('file', new Blob([`role probe ${stamp}\n`], { type: 'text/plain' }), 'TANTRA-ROLE-PROBE.txt');
    const upload = await fetchWithRetry(`${SITE}/api/v1/documents/upload`, {
      method: 'POST',
      headers: { authorization: `Bearer ${roleToken}` },
      body: form,
    });
    const uploadBody = await upload.json().catch(() => ({}));
    record(
      'T6b',
      'Claim: a read-only researcher is refused uploads with 403 "This role is read-only"',
      upload.status === 403 && /read-only/i.test(`${uploadBody?.error?.message ?? uploadBody?.message ?? ''}`) ? 'pass' : 'fail',
      `role=${loginBody?.user?.role ?? 'n/a'} (seeded), upload status=${upload.status}, message="${uploadBody?.error?.message ?? uploadBody?.message ?? 'n/a'}"`,
    );
    const researcherDocs = await api(roleToken, '/documents?page_size=5');
    record(
      'T6c',
      'A researcher can still read the shared law library',
      (researcherDocs.body?.items ?? []).length > 0 ? 'pass' : 'fail',
      `library documents visible=${(researcherDocs.body?.items ?? []).length}`,
    );
  } else {
    record(
      'T6b',
      'Claim: a read-only researcher is refused uploads with 403 "This role is read-only"',
      'blocked',
      `seeded researcher login failed: ${login.status}`,
    );
  }
} else {
  record(
    'T6b',
    'Claim: a read-only researcher is refused uploads with 403 "This role is read-only"',
    'blocked',
    `signup ignores role (created role=${roleBody?.user?.role ?? 'n/a'}); set RESEARCHER_EMAIL/RESEARCHER_PASSWORD to exercise the seeded read-only account`,
  );
}

// ------------------------------------------- defect 2 on mobile: hamburger nav
const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
const pageM = await mobileContext.newPage();
pageM.on('pageerror', (error) => console.log('PAGEERROR(mobile)', error.message));
await signIn(pageM, account.token);
const mobileChecks = [
  ['calendar', 'Calendar', '/calendar'],
  ['settings', 'Settings', '/settings'],
];
for (const [index, [slug, linkName, expectedPath]] of mobileChecks.entries()) {
  let ok = false;
  let detail = '';
  try {
    await pageM.goto(`${SITE}/dashboard`, { waitUntil: 'networkidle' });
    await shot(pageM, `25-mobile-0-${slug}-start`);
    await pageM.getByRole('button', { name: 'Open navigation' }).click();
    await pageM.waitForTimeout(600);
    const nav = pageM.getByRole('navigation', { name: 'Main navigation' });
    await nav.getByRole('link', { name: linkName }).click();
    await pageM.waitForTimeout(2500);
    ok = pageM.url().includes(expectedPath) && (await pageM.locator('main').innerText()).length > 60;
    detail = `landed=${pageM.url().replace(SITE, '')}, main chars=${(await pageM.locator('main').innerText()).length}`;
  } catch (error) {
    detail = `error: ${error.message.split('\n')[0]}`;
  }
  record(
    `D2m-${index + 1}`,
    `Claim: the ${slug} control does not work on a phone (390x844)`,
    ok ? 'not confirmed' : 'confirmed',
    detail,
    await shot(pageM, `25-mobile-${index + 1}-${slug}`),
  );
}
await mobileContext.close();

await browser.close();

writeSummary();
await browser.close().catch(() => {});
const failing = results.filter((item) => item.verdict === 'confirmed' || item.verdict === 'fail');
console.log(`failures/confirmed defects: ${failing.length}`);
