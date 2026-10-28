'use client';
import { useParams } from 'next/navigation';
import { CaseForm } from '@/features/cases/components/case-form';
export default function EditCasePage() {
  const { id } = useParams<{ id: string }>();
  return <CaseForm caseId={id} />;
}
