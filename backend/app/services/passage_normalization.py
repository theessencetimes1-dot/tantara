"""Normalize passage text for retrieval and answer-level duplicate checks."""

import re


def normalize_passage(value: str) -> str:
    """Fold whitespace/case and ignore an immediately repeated leading header line."""
    lines = [re.sub(r"\s+", " ", line).strip().casefold() for line in value.splitlines()]
    lines = [line for line in lines if line]
    while len(lines) > 1 and lines[0] == lines[1]:
        lines.pop(0)
    return "\n".join(lines)
