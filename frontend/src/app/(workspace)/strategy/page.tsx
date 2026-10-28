import { Suspense } from 'react';
import { StrategyPanel } from '@/features/strategy';

export default function StrategyPage() {
  return (
    <Suspense
      fallback={
        <div className="strategy-page">
          <div role="status">Opening Strategy Advisor…</div>
        </div>
      }
    >
      <StrategyPanel />
    </Suspense>
  );
}
