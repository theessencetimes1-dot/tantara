export const WORKSPACE_TIME_ZONE = process.env.NEXT_PUBLIC_WORKSPACE_TIME_ZONE || 'Asia/Kolkata';

function parts(value: Date, timeZone = WORKSPACE_TIME_ZONE) {
  const result = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value);
  return Object.fromEntries(result.map(({ type, value }) => [type, Number(value)]));
}

export function workspaceDateTimeInput(value?: string | null): string {
  if (!value) return '';
  const instant = new Date(value);
  if (Number.isNaN(instant.valueOf())) return '';
  const date = parts(instant);
  return `${date.year}-${String(date.month).padStart(2, '0')}-${String(date.day).padStart(2, '0')}T${String(date.hour).padStart(2, '0')}:${String(date.minute).padStart(2, '0')}`;
}

export function workspaceDateTimeIso(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, y, mo, d, h, mi] = match.map(Number);
  const wallAsUtc = Date.UTC(y, mo - 1, d, h, mi);
  let instant = wallAsUtc;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const zoned = parts(new Date(instant));
    const representedAsUtc = Date.UTC(
      zoned.year,
      zoned.month - 1,
      zoned.day,
      zoned.hour,
      zoned.minute,
      zoned.second,
    );
    instant += wallAsUtc - representedAsUtc;
  }
  const offsetMinutes = Math.round((wallAsUtc - instant) / 60_000);
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absolute = Math.abs(offsetMinutes);
  const offset = `${sign}${String(Math.floor(absolute / 60)).padStart(2, '0')}:${String(absolute % 60).padStart(2, '0')}`;
  return `${value}:00${offset}`;
}

export function workspaceDateKey(value: Date | string, timeZone = WORKSPACE_TIME_ZONE): string {
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = value instanceof Date ? value : new Date(value);
  const dateParts = parts(date, timeZone);
  return `${dateParts.year}-${String(dateParts.month).padStart(2, '0')}-${String(dateParts.day).padStart(2, '0')}`;
}

export function calendarDay(year: number, monthIndex: number, day: number): Date {
  return new Date(Date.UTC(year, monthIndex, day, 12));
}

export function calendarDayOffset(date: Date, days: number): Date {
  return calendarDay(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days);
}

export function calendarDateParts(date: Date) {
  return { year: date.getUTCFullYear(), month: date.getUTCMonth(), day: date.getUTCDate() };
}

export function workspaceDateTimeDisplay(
  value: string | Date,
  options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' },
): string {
  const raw = value instanceof Date ? value.toISOString() : value;
  const zonedValue =
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)
      ? (workspaceDateTimeIso(value.slice(0, 16)) ?? value)
      : raw;
  const instant = new Date(zonedValue);
  if (Number.isNaN(instant.valueOf())) return raw;
  return `${new Intl.DateTimeFormat('en', { ...options, timeZone: WORKSPACE_TIME_ZONE }).format(instant)} · ${WORKSPACE_TIME_ZONE}`;
}
