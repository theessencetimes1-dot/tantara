import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const repoRoot = path.resolve(__dirname, '..');
const apiOrigin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
const webBase = process.env.TANTARA_WEB_URL ?? 'http://127.0.0.1:3010';
const apiPort = Number(process.env.TANTARA_API_PORT ?? (new URL(apiOrigin).port || 8010));
const webPort = Number(process.env.TANTARA_WEB_PORT ?? (new URL(webBase).port || 3010));
const testDataDir =
  process.env.TANTARA_TEST_DATA_DIR ?? mkdtempSync(path.join(os.tmpdir(), 'tantara-playwright-'));
const python = process.env.TANTARA_PYTHON ?? path.join(repoRoot, 'backend/.venv/bin/python');
process.env.TANTARA_API_ORIGIN = apiOrigin;
process.env.TANTARA_WEB_URL = webBase;
process.env.TANTARA_WEB_URL = webBase;
process.env.TANTARA_TEST_DATA_DIR = testDataDir;
process.env.TANTARA_PYTHON = python;

export default defineConfig({
  testDir: './tests',
  // All browser tests share this run's migrated SQLite database and deterministic seed.
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  projects: [
    {
      name: 'desktop',
      testIgnore: /documents-round(4|5)-mobile\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        timezoneId: 'UTC',
        baseURL: webBase,
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'mobile',
      testMatch: /documents-round(4|5)-mobile\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        timezoneId: 'UTC',
        baseURL: webBase,
        viewport: { width: 390, height: 844 },
      },
    },
  ],
  webServer: [
    {
      command: `"${python}" ../scripts/seed.py --demo && "${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiOrigin}/health`,
      cwd: path.join(repoRoot, 'backend'),
      env: {
        ...process.env,
        TANTARA_DATA_DIR: testDataDir,
        DATABASE_URL: `sqlite:///${path.join(testDataDir, 'tantara.db')}`,
      },
      reuseExistingServer: false,
      timeout: 240000,
    },
    {
      command: `pnpm exec next dev -H 127.0.0.1 -p ${webPort}`,
      url: webBase,
      cwd: path.join(repoRoot, 'frontend'),
      env: { ...process.env, TANTARA_API_ORIGIN: apiOrigin, NEXT_PUBLIC_API_BASE_URL: '' },
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
  globalTeardown: './tests/global-teardown.ts',
});
