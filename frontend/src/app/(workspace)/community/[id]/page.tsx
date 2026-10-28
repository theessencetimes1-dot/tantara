import { CommunityThread } from '@/features/community/Community';
export default async function CommunityThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CommunityThread id={id} />;
}
