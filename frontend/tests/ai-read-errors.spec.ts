import { expect, test } from '@playwright/test';
import { ApiError } from '../src/lib/api/client';
import { aiFailureMessage, classifyAiFailure } from '../src/features/documents/ai-read-errors';

test('document extraction distinguishes authentication and each service failure category', () => {
  expect(classifyAiFailure(new ApiError(401, 'unauthorized', 'Denied'), 'model_unavailable')).toBe(
    'auth_failure',
  );
  expect(classifyAiFailure(new Error('embedding service failed'), 'embedding_failure')).toBe(
    'embedding_failure',
  );
  expect(classifyAiFailure(new Error('extract failed'), 'extraction_failure')).toBe('extraction_failure');
  expect(classifyAiFailure(new Error('response could not load'), 'response_loading_failure')).toBe(
    'response_loading_failure',
  );
  expect(classifyAiFailure(new Error('connection refused'), 'model_unavailable')).toBe('model_unavailable');
  const messages = [
    'auth_failure',
    'embedding_failure',
    'extraction_failure',
    'response_loading_failure',
    'model_unavailable',
  ] as const;
  expect(new Set(messages.map((category) => aiFailureMessage(category))).size).toBe(messages.length);
});
