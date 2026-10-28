export const keys = {
  summary: ['dashboard', 'summary'] as const,
  activity: ['dashboard', 'activity'] as const,
  upcoming: ['dashboard', 'upcoming'] as const,
  cases: (q: string) => ['cases', q] as const,
  settings: (section: string) => ['settings', section] as const,
};
