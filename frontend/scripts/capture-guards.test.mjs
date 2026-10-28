import assert from 'node:assert/strict';
import test from 'node:test';
import { assertCaptureReady } from './capture-guards.mjs';

test('capture readiness rejects the PDF loading state', () => {
  assert.throws(
    () => assertCaptureReady('/documents', 'Preview Loading PDF pages…'),
    /while loading text is visible/,
  );
});

test('documents capture requires a rendered PDF page after loading ends', () => {
  assert.throws(
    () => assertCaptureReady('/documents', 'Preview Page 1'),
    /before the PDF preview has rendered/,
  );
  assert.doesNotThrow(() =>
    assertCaptureReady('/documents', 'Preview Page 1', { hasRenderedDocumentPage: true }),
  );
  assert.doesNotThrow(() =>
    assertCaptureReady('/documents', 'Document list', {
      requireRenderedDocumentPage: false,
    }),
  );
});
