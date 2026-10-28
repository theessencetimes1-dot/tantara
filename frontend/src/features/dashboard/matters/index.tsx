'use client';
import { CaseList } from '@/features/cases/components/case-list';
export function MattersCard() {
  return (
    <div style={{ marginTop: 15 }}>
      <CaseList compact />
    </div>
  );
}
