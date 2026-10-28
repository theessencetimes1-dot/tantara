'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import { toast } from 'sonner';
import '../styles.css';
type Strategy = {
  case_theory?: string;
  key_issues?: string[];
  legal_arguments?: Array<Record<string, unknown>>;
  counterarguments?: string[];
  strategy_plan?: string;
};
const tabs = [
  'Case Theory',
  'Key Issues',
  'Legal Arguments',
  'Anticipated Counters',
  'Strategy Plan',
] as const;
export function StrategyPanel({ id }: { id: string }) {
  const [tab, T] = useState<(typeof tabs)[number]>(tabs[0]),
    [value, V] = useState('');
  const q = useQuery({
    queryKey: ['strategy', id],
    queryFn: () => api.get<Strategy>(`/cases/${id}/strategy`),
    refetchOnWindowFocus: false,
  });
  const data = q.data;
  const text =
    tab === 'Case Theory'
      ? data?.case_theory || ''
      : tab === 'Strategy Plan'
        ? data?.strategy_plan || ''
        : JSON.stringify(
            tab === 'Key Issues'
              ? data?.key_issues
              : tab === 'Legal Arguments'
                ? data?.legal_arguments
                : data?.counterarguments,
            null,
            2,
          ) || '';
  const save = async () => {
    try {
      const key =
        tab === 'Case Theory'
          ? 'case_theory'
          : tab === 'Strategy Plan'
            ? 'strategy_plan'
            : tab === 'Key Issues'
              ? 'key_issues'
              : tab === 'Legal Arguments'
                ? 'legal_arguments'
                : 'counterarguments';
      const nextValue = tab === 'Case Theory' || tab === 'Strategy Plan' ? value : JSON.parse(value);
      await api.put(`/cases/${id}/strategy`, { ...data, [key]: nextValue });
      await q.refetch();
      toast.success('Strategy saved');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unable to save strategy');
    }
  };
  return (
    <div>
      <div className="matter-tabs">
        {tabs.map((x) => (
          <button
            key={x}
            className={x === tab ? 'active' : ''}
            onClick={() => {
              T(x);
              V('');
            }}
          >
            {x}
          </button>
        ))}
      </div>
      {q.isLoading ? (
        <p>Loading strategy…</p>
      ) : q.isError ? (
        <p className="matter-error">Strategy is unavailable.</p>
      ) : (
        <>
          <div style={{ padding: 12 }}>
            <textarea
              aria-label={tab}
              value={value || text}
              onChange={(e) => V(e.target.value)}
              rows={8}
              style={{
                width: '100%',
                border: '1px solid #dce2eb',
                borderRadius: 8,
                padding: 12,
              }}
            />
            {tab === 'Legal Arguments' && (
              <p className="subheading">
                Arguments with citations are source supported; entries without source citations are
                hypotheses. Check each citation before relying on it.
              </p>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'end', gap: 9 }}>
            <button
              onClick={async () => {
                try {
                  await api.post(`/cases/${id}/strategy/generate`);
                  await q.refetch();
                  toast.success('Strategy generated');
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : 'Unable to generate strategy');
                }
              }}
            >
              Generate strategy
            </button>
            <button className="matter-action" onClick={() => void save()}>
              Save strategy
            </button>
          </div>
        </>
      )}
    </div>
  );
}
