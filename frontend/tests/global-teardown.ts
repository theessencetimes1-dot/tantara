import { rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export default async function globalTeardown() {
  const dataDir = process.env.TANTARA_TEST_DATA_DIR;
  if (
    dataDir &&
    path.dirname(dataDir) === os.tmpdir() &&
    path.basename(dataDir).startsWith('tantara-playwright-')
  ) {
    rmSync(dataDir, { recursive: true, force: true });
  }
}
