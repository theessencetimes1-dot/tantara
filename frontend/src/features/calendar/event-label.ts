export type CalendarEventLabelSource = {
  title?: string;
  type?: string;
  event_type?: string;
};

const eventLabels: Record<string, string> = {
  all_day_event: 'All day',
  event: 'All day',
  deadline: 'Deadline',
  first_hearing: 'First hearing',
  hearing_completed: 'Hearing completed',
};

export function calendarEventLabel(event: CalendarEventLabelSource): string {
  const title = (event.title || '').trim();
  if (event.type === 'event') {
    return eventLabels[event.event_type || ''] || eventLabels.event;
  }
  return (
    eventLabels[event.type || ''] ||
    eventLabels[event.event_type || ''] ||
    eventLabels[title] ||
    (title || event.event_type || 'Case event').replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  );
}
