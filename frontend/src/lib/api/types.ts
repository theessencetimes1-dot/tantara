export type User = {
  id: string;
  name: string;
  first_name?: string;
  email: string;
  role: string;
  avatar_initials?: string;
  title?: string;
};
export type Summary = {
  greeting: string;
  first_name: string;
  today: string;
  active_cases: number;
  pending_arbitrations: number;
  hearings_this_week: number;
  documents_processed: number;
  drafts_in_progress: number;
  tasks_due: number;
  tasks_overdue?: number;
  is_demo?: boolean;
};
export type Activity = {
  id: string;
  type: string;
  actor?: string;
  title: string;
  case_id?: string;
  at: string;
};
export type Upcoming = {
  id: string;
  type: 'hearing' | 'deadline' | 'event';
  title: string;
  case_id?: string;
  case_title?: string;
  at: string;
  due_in_days: number;
  event_type?: string;
};
export type Case = { id: string; title: string; reference_number?: string; status?: string };
export type SettingsData = Record<string, unknown>;
