'use client';
import { useParams } from 'next/navigation';
import { StrategyPanel } from '@/features/strategy/strategy-panel';
export default function CaseStrategyPage() {
  const { id } = useParams<{ id: string }>();
  return <StrategyPanel caseId={id} />;
}
