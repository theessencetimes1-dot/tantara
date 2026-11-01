export function getUploadQueueStateLabel(job) {
  const status = String(job?.status ?? 'queued').toLowerCase();
  const steps = Array.isArray(job?.steps) ? job.steps : [];
  const lastStep = steps.at(-1);
  const step =
    typeof lastStep === 'object' && lastStep !== null
      ? `${lastStep.key ?? ''} ${lastStep.label ?? ''}`.toLowerCase()
      : String(lastStep ?? '').toLowerCase();

  return status === 'ready' || status === 'completed'
    ? 'Ready'
    : status === 'failed'
      ? 'Failed'
      : status === 'extracting'
        ? 'Checking text and creating embeddings'
        : status === 'indexing' || status === 'running'
          ? 'Indexing'
          : step.includes('index') || step.includes('embed') || step.includes('chunk')
            ? 'Indexing'
            : step.includes('extract') || status === 'processing'
              ? 'Extracting'
              : 'Uploading';
}

export function getUploadQueueSteps(job) {
  return Array.isArray(job?.steps)
    ? job.steps.map((step) =>
        typeof step === 'object' && step !== null ? String(step.label ?? step.key ?? '') : String(step ?? ''),
      )
    : [];
}
