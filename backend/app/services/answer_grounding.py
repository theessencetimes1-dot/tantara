"""Select exact source passages and keep case-record context explicitly separate."""

import re

from app.services.passage_normalization import normalize_passage

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "by",
    "did",
    "does",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "what",
    "which",
    "who",
    "will",
    "with",
}

_FIELD_PATTERNS = {
    "seat": re.compile(r"\bseat\b|place of arbitration|where.{0,40}tribunal.{0,20}sit", re.I),
    "forum": re.compile(r"\bforum\b|\bcourt\b|\btribunal\b", re.I),
    "governing_law": re.compile(r"governing law|applicable law", re.I),
    "claimant": re.compile(r"\bclaimant\b", re.I),
    "respondent": re.compile(r"\brespondent\b", re.I),
    "reference_number": re.compile(r"reference number|case number", re.I),
}

_FIELD_VALUE_PATTERNS = {
    "seat": re.compile(r"\bseat\s+(?:of arbitration\s+)?(?:is|shall be|will be|was|:)?\s*([^,.;\n]+)", re.I),
    "forum": re.compile(r"\b(?:forum|court|tribunal)\s+(?:is|shall be|will be|was|:)?\s*([^,.;\n]+)", re.I),
    "governing_law": re.compile(
        r"\b(?:governing|applicable) law\s+(?:is|shall be|will be|was|:)?\s*([^,.;\n]+)", re.I
    ),
    "claimant": re.compile(r"\bclaimant\s+(?:is|:)?\s*([^,.;\n]+)", re.I),
    "respondent": re.compile(r"\brespondent\s+(?:is|:)?\s*([^,.;\n]+)", re.I),
}


def requested_field(question: str) -> str | None:
    for field in ("seat", "governing_law", "claimant", "respondent", "reference_number", "forum"):
        if _FIELD_PATTERNS[field].search(question):
            return field
    return None


def _sentences(text: str):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _query_terms(question: str):
    return {
        term.lower()
        for term in re.findall(r"[\w-]+", question)
        if len(term) > 1 and term.lower() not in _STOP_WORDS
    }


def select_supports(question: str, hits: list[dict], limit: int = 3):
    """Return exact hit substrings, prioritizing sentences that answer the asked field."""
    field = requested_field(question)
    terms = _query_terms(question)
    candidates = []
    for hit in hits:
        content = hit["snippet"]
        for sentence in _sentences(content):
            if field:
                pattern = _FIELD_PATTERNS[field]
                if not pattern.search(sentence):
                    continue
                field_match = 1
            else:
                field_match = 0
            words = {term.lower() for term in re.findall(r"[\w-]+", sentence)}
            overlap = len(terms & words)
            if not field and overlap < 1:
                continue
            candidates.append(
                (
                    (field_match, overlap, hit.get("retrieval_score", 0)),
                    {
                        "chunk_id": hit["chunk_id"],
                        "document_id": hit["document_id"],
                        "page_number": hit["page_number"],
                        "quote": sentence,
                        "_hit": hit,
                    },
                )
            )
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    supports = []
    seen_chunks = set()
    seen_quotes = set()
    for _rank, support in candidates:
        normalized_quote = normalize_passage(support["quote"])
        if support["chunk_id"] in seen_chunks or normalized_quote in seen_quotes:
            continue
        seen_chunks.add(support["chunk_id"])
        seen_quotes.add(normalized_quote)
        supports.append(support)
        if len(supports) == limit:
            break
    return supports


def extract_field_value(field: str, quote: str) -> str | None:
    pattern = _FIELD_VALUE_PATTERNS.get(field)
    if pattern is None:
        return None
    match = pattern.search(quote)
    if not match:
        return None
    return match.group(1).strip().strip("\"'“”") or None


def values_differ(left, right) -> bool:
    return " ".join(str(left).casefold().split()) != " ".join(str(right).casefold().split())
