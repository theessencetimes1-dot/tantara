def chunk_text(text: str, chunk_size: int = 1800, overlap: int = 250):
    text = "\n".join(line.rstrip() for line in text.replace("\x00", "").splitlines()).strip()
    if not text:
        return []
    if chunk_size < 100 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunk size/overlap")
    chunks, start, idx = [], 0, 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + chunk_size // 2, end),
                text.rfind(". ", start + chunk_size // 2, end),
                text.rfind(" ", start + chunk_size // 2, end),
            )
            if boundary > start:
                end = boundary + (1 if text[boundary] == "\n" else 0)
        piece = text[start:end].strip()
        if piece:
            chunks.append({"content": piece, "chunk_index": idx, "start_char": start, "end_char": end})
            idx += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
