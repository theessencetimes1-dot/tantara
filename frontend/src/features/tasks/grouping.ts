export type TaskForGrouping = { status: string; due_at?: string | null };
import { WORKSPACE_TIME_ZONE, workspaceDateKey } from '@/lib/datetime';

export { WORKSPACE_TIME_ZONE };

function dateKey(value: Date): string {
  return workspaceDateKey(value);
}

export function taskGroup(task: TaskForGrouping, now: Date): string {
  if (['done', 'completed'].includes(task.status.toLowerCase())) return 'Done';
  if (!task.due_at) return 'No due date';
  const due = new Date(task.due_at);
  if (Number.isNaN(due.valueOf())) return 'No due date';
  const dueKey = dateKey(due);
  const todayKey = dateKey(now);
  if (dueKey < todayKey) return 'Overdue';
  if (dueKey === todayKey) return 'Today';
  const todayAtNoon = new Date(`${todayKey}T12:00:00Z`);
  const weekday = (todayAtNoon.getUTCDay() + 6) % 7;
  const monday = new Date(todayAtNoon);
  monday.setUTCDate(monday.getUTCDate() - weekday);
  const nextMonday = new Date(monday);
  nextMonday.setUTCDate(nextMonday.getUTCDate() + 7);
  const dueAtNoon = new Date(`${dueKey}T12:00:00Z`);
  return dueAtNoon < nextMonday ? 'This week' : 'Later';
}
