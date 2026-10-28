import { ApiError } from '@/lib/api/client';

export type AiFailure =
  | 'auth_failure'
  | 'embedding_failure'
  | 'extraction_failure'
  | 'response_loading_failure'
  | 'model_unavailable';

export function classifyAiFailure(error: unknown, fallback: AiFailure): AiFailure {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return 'auth_failure';
  return fallback;
}

export function aiFailureMessage(failure: AiFailure) {
  const messages: Record<AiFailure, string> = {
    auth_failure: 'Your access could not be verified. Sign in again, then retry document extraction.',
    embedding_failure:
      'The embedding service could not prepare document passages. Retry when it is available.',
    extraction_failure: 'The document extraction request failed. No new candidate fields were saved.',
    response_loading_failure:
      'The extraction finished, but its response could not be loaded. Retry document extraction.',
    model_unavailable: 'The configured model could not respond. No model-generated fields are available.',
  };
  return messages[failure];
}
