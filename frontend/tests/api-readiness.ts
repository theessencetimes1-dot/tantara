export async function requirePlaywrightApi() {
  const origin = process.env.TANTARA_API_ORIGIN ?? 'http://127.0.0.1:8010';
  const healthUrl = new URL('/health', origin).toString();
  let observed = 'unreachable';
  try {
    const response = await fetch(healthUrl, { signal: AbortSignal.timeout(5000) });
    observed = `HTTP ${response.status}`;
    if (response.ok) return;
  } catch (error) {
    observed = error instanceof Error ? error.message : String(error);
  }
  const backendLog =
    process.env.TANTARA_BACKEND_LOG_FILE ?? '(Playwright backend webServer log path is not configured)';
  throw new Error(
    `Required Playwright API health check failed at ${healthUrl} (${observed}). ` +
      `Inspect the Playwright backend webServer log: ${backendLog}`,
  );
}
