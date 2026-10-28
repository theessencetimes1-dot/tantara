'use client';
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '@/lib/api/endpoints';
import { api } from '@/lib/api/client';
import * as Dialog from '@radix-ui/react-dialog';
import Link from 'next/link';
import '../cases/styles.css';
import { taskGroup } from './grouping';
import { WORKSPACE_TIME_ZONE, workspaceDateTimeInput, workspaceDateTimeIso } from '@/lib/datetime';

type Task = {
  id: string;
  title: string;
  status: string;
  priority?: string;
  due_at?: string | null;
  notes?: string;
  case_id?: string;
  case_title?: string;
};
const groups = ['Overdue', 'Today', 'This week', 'Later', 'No due date', 'Done'];
function taskDueLabel(value: string) {
  const input = workspaceDateTimeInput(value);
  const date = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeZone: WORKSPACE_TIME_ZONE });
  if (input.endsWith('T00:00')) return `${date.format(new Date(value))} · Deadline`;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: WORKSPACE_TIME_ZONE,
  }).format(new Date(value));
}
export default function TasksPage() {
  const [show, setShow] = useState(false);
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [priority, setPriority] = useState('medium');
  const [status, setStatus] = useState('todo');
  const [notes, setNotes] = useState('');
  const [caseId, setCaseId] = useState('');
  const [editing, setEditing] = useState<Task | null>(null);
  const [actionMenu, setActionMenu] = useState<string | null>(null);
  const [now] = useState(() => new Date());
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['tasks'],
    queryFn: () => endpoints.tasks.list('?page_size=100'),
  });
  const casesQuery = useQuery({
    queryKey: ['task-case-options'],
    queryFn: () => api.get<{ items: Array<{ id: string; title: string }> }>('/cases?page_size=100'),
  });
  const complete = async (t: Task) => {
    const old = q.data;
    if (!old) return;
    qc.setQueryData(['tasks'], {
      ...old,
      items: (old.items as Task[]).map((x: Task) =>
        x.id === t.id ? { ...x, status: x.status === 'done' ? 'open' : 'done' } : x,
      ),
    });
    try {
      await endpoints.tasks.update(t.id, {
        status: t.status === 'done' ? 'todo' : 'done',
      });
    } catch {
      qc.setQueryData(['tasks'], old);
      window.alert('Task update failed; previous status restored.');
    }
  };
  const items: Task[] = (q.data?.items || []) as Task[];
  const cases = (casesQuery.data?.items || []) as Array<{
    id: string;
    title: string;
  }>;
  const caseTitles = new Map(cases.map((c) => [c.id, c.title]));
  const openTask = (task?: Task) => {
    setEditing(task || null);
    setTitle(task?.title || '');
    setDue(workspaceDateTimeInput(task?.due_at));
    setPriority(task?.priority || 'medium');
    setStatus(task?.status || 'todo');
    setNotes(task?.notes || '');
    setCaseId(task?.case_id || '');
    setShow(true);
  };
  return (
    <section className="matter-wrap">
      <div className="matter-head">
        <div>
          <h1 className="matter-title">Tasks</h1>
          <p className="subheading">Your casework, organized</p>
        </div>
        <button className="matter-action" onClick={() => openTask()}>
          ＋ New task
        </button>
      </div>
      {q.isError ? (
        <div className="matter-error">
          Tasks are unavailable.{' '}
          <button className="task-retry" onClick={() => void q.refetch()}>
            Retry
          </button>
        </div>
      ) : q.isLoading ? (
        <div className="matter-card matter-skeleton" />
      ) : (
        <div className="task-groups">
          {groups.map((name) => {
            const tasks = items.filter((task) => taskGroup(task, now) === name);
            if (!tasks.length) return null;
            return (
              <section className="matter-card task-group" key={name}>
                <h2>
                  {name} <small>{tasks.length}</small>
                </h2>
                {tasks.length
                  ? tasks.map((task) => (
                      <div className="task-row" key={task.id}>
                        <input
                          type="checkbox"
                          aria-label={`Complete ${task.title}`}
                          checked={task.status === 'done' || task.status === 'completed'}
                          onChange={() => void complete(task)}
                        />
                        <button className="task-edit-title" title="Edit task" onClick={() => openTask(task)}>
                          {task.title}
                        </button>
                        <span className="task-due">
                          {task.due_at ? taskDueLabel(task.due_at) : 'No due date'}
                          {name === 'Overdue' ? ' · Overdue' : ''}
                        </span>
                        <span
                          className={`task-priority priority-${(task.priority || 'normal').toLowerCase()}`}
                        >
                          {task.priority || 'Normal'}
                        </span>
                        {task.case_id ? (
                          <Link className="task-case" href={`/cases/${task.case_id}`}>
                            {task.case_title || caseTitles.get(task.case_id) || 'Linked case'}
                          </Link>
                        ) : (
                          <span className="task-case muted">No linked case</span>
                        )}
                        <div className="task-row-actions">
                          <button
                            className="matter-more"
                            aria-label={`Actions for ${task.title}`}
                            aria-expanded={actionMenu === task.id}
                            onClick={() => setActionMenu(actionMenu === task.id ? null : task.id)}
                          >
                            ⋯
                          </button>
                          {actionMenu === task.id && (
                            <div className="task-action-menu">
                              <button
                                title="Edit task"
                                onClick={() => {
                                  setActionMenu(null);
                                  openTask(task);
                                }}
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => {
                                  setActionMenu(null);
                                  void complete(task);
                                }}
                              >
                                Mark {task.status === 'done' || task.status === 'completed' ? 'open' : 'done'}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  : null}
              </section>
            );
          })}
        </div>
      )}
      <Dialog.Root open={show} onOpenChange={setShow}>
        <Dialog.Portal>
          <Dialog.Overlay className="matter-dialog-overlay" />
          <Dialog.Content className="matter-dialog">
            <Dialog.Title>{editing ? 'Edit task' : 'New task'}</Dialog.Title>
            <Dialog.Description>Create a task for your casework.</Dialog.Description>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const payload = {
                    title,
                    due_at: due ? workspaceDateTimeIso(due) : null,
                    status,
                    priority,
                    notes,
                    case_id: caseId || null,
                  };
                  if (editing) await endpoints.tasks.update(editing.id, payload);
                  else await endpoints.tasks.create(payload);
                  setShow(false);
                  setEditing(null);
                  await q.refetch();
                } catch (err) {
                  window.alert(err instanceof Error ? err.message : 'Unable to create task');
                }
              }}
            >
              <label>
                Title
                <input
                  aria-label="Task title"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                Due date and time
                <input
                  aria-label="Due date and time"
                  type="datetime-local"
                  value={due}
                  onChange={(e) => setDue(e.target.value)}
                />
              </label>
              <label>
                Priority
                <select
                  aria-label="Task priority"
                  value={priority}
                  onChange={(event) => setPriority(event.target.value)}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label>
                Status
                <select
                  aria-label="Task status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="todo">To do</option>
                  <option value="in_progress">In progress</option>
                  <option value="done">Done</option>
                </select>
              </label>
              <label>
                Linked case
                <select
                  aria-label="Linked case"
                  value={caseId}
                  onChange={(event) => setCaseId(event.target.value)}
                >
                  <option value="">No case</option>
                  {casesQuery.data?.items.map((item: { id: string; title: string }) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Notes
                <textarea
                  aria-label="Task notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </label>
              <div className="matter-dialog-actions">
                <button type="button" onClick={() => setShow(false)}>
                  Cancel
                </button>
                <button className="matter-action">Save task</button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
