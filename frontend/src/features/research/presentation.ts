import type { ResearchSource } from './api';
import { documentPageUrl } from './document-url';

export type CitationGroup = {
  documentId: string;
  title: string;
  pages: Array<{
    page: number;
    sources: ResearchSource[];
    bestScore?: number;
    rank: number;
  }>;
  excerptGroups: Array<{ excerpt: string; sources: ResearchSource[] }>;
};

export function citationLabel(page: number): string {
  return `Page ${page}`;
}

export function citationAccessibleLabel(source: ResearchSource): string {
  return `${normalizeDocumentTitle(source.document_title ?? 'Untitled document')} · ${citationLabel(source.page_number)}`;
}

export function citationLink(source: ResearchSource) {
  return {
    label: citationAccessibleLabel(source),
    href: documentPageUrl(source.document_id, source.page_number, source.chunk_id),
    chunkId: source.chunk_id,
  };
}

export function normalizeDocumentTitle(title: string): string {
  return title
    .replace(/\\n/g, ' ')
    .replace(/[\r\n]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function groupSources(sources: ResearchSource[]): CitationGroup[] {
  const groups = new Map<string, CitationGroup>();
  for (const source of sources) {
    let group = groups.get(source.document_id);
    if (!group) {
      group = {
        documentId: source.document_id,
        title: normalizeDocumentTitle(source.document_title ?? 'Untitled document'),
        pages: [],
        excerptGroups: [],
      };
      groups.set(source.document_id, group);
    }
    let page = group.pages.find((entry) => entry.page === source.page_number);
    if (!page) {
      page = { page: source.page_number, sources: [], rank: sources.indexOf(source) + 1 };
      group.pages.push(page);
    }
    page.sources.push(source);
    const excerpt = source.excerpt?.trim() ?? '';
    if (excerpt) {
      let excerptGroup = group.excerptGroups.find((entry) => entry.excerpt === excerpt);
      if (!excerptGroup) {
        excerptGroup = { excerpt, sources: [] };
        group.excerptGroups.push(excerptGroup);
      }
      excerptGroup.sources.push(source);
    }
    const score = source.retrieval_score ?? source.retreival_score ?? source.score;
    if (score != null && Number.isFinite(score)) {
      page.bestScore = page.bestScore == null ? score : Math.max(page.bestScore, score);
    }
  }
  return [...groups.values()].map((group) => ({
    ...group,
    pages: group.pages.sort((a, b) => a.page - b.page),
  }));
}

export function answerStatusLabel(status: string, answerKind?: string, generationKind?: string): string {
  switch (status) {
    case 'ok':
    case 'answered':
      if (answerKind === 'model_generated' || generationKind === 'model_generated')
        return 'Model response · review sources';
      if (answerKind === 'case_record' || generationKind === 'case_record') return 'From the case record';
      if (answerKind || generationKind) return 'Retrieved material only';
      return 'Response returned · provenance unavailable';
    case 'model_unavailable':
      return 'Evidence only — model unavailable';
    case 'no_evidence':
      return 'No supporting excerpts';
    case 'embedding_unavailable':
      return 'Lexical only — embeddings unavailable';
    default:
      return 'Research error';
  }
}
