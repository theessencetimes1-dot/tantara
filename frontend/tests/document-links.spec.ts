import { test, expect } from '@playwright/test';
import { documentHref } from '../src/features/documents/links';

test('document links preserve the citation page in the URL', () => {
  expect(documentHref('doc/with spaces', 2)).toBe('/documents/doc%2Fwith%20spaces?page=2');
  expect(documentHref('doc-123')).toBe('/documents/doc-123');
  expect(documentHref('doc-123', 0)).toBe('/documents/doc-123');
});
