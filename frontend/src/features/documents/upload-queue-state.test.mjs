import assert from 'node:assert/strict';
import test from 'node:test';
import { getUploadQueueStateLabel, getUploadQueueSteps } from './upload-queue-state.mjs';

test('upload queue renders a state for a freshly claimed job without status or steps', () => {
  const job = { status: null, steps: undefined };

  assert.equal(getUploadQueueStateLabel(job), 'Uploading');
  assert.deepEqual(getUploadQueueSteps(job), []);
});
