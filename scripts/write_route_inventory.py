#!/usr/bin/env python3
"""Regenerate docs/BACKEND_ROUTES.txt from the checked-in OpenAPI contract."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def render_inventory():
    schema = json.loads((ROOT / "backend" / "openapi.json").read_text())
    lines = [
        "# Generated from backend/openapi.json. Regenerate with scripts/write_route_inventory.py.",
        "",
    ]
    lines.extend(
        f"{method.upper()} {path}"
        for path, operations in sorted(schema["paths"].items())
        for method in sorted(operations)
        if method in METHODS
    )
    return "\n".join(lines) + "\n"


def render_method_matrix():
    schema = json.loads((ROOT / "backend" / "openapi.json").read_text())
    matrix_path = ROOT / "docs" / "TEST_MATRIX.md"
    current = matrix_path.read_text().split("\n## Method-level expansion\n", 1)[0]
    by_path = {}
    for line in current.splitlines():
        if not line.startswith("| ") or "OpenAPI path" in line or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("| ").split("|")]
        if len(cells) == 8:
            by_path[cells[1]] = cells[2:]
    lines = [
        "## Method-level expansion",
        "",
        "Rows below expand each OpenAPI method separately. Shared dynamic tests enumerate each protected method; body-bearing mutations are individually submitted with invalid payloads and checked for the standard 422 envelope. The success/isolation references point to the resource-specific cases in the preceding matrix.",
        "",
        "| Method | Path | Success | 422 validation | 401/403 | 404 | User isolation | Edge case |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for path, operations in sorted(schema["paths"].items()):
        for method in sorted(operations):
            if method not in METHODS:
                continue
            cells = by_path.get(
                path,
                [
                    "See route-specific tests",
                    "N/A",
                    "test_all_protected_openapi_operations_reject_anonymous_requests",
                    "N/A",
                    "See owner-scoping tests",
                    "N/A",
                ],
            )
            success, validation, auth, missing, isolation, edge = cells
            operation = operations[method]
            if not operation.get("requestBody") and method in {"post", "put", "patch"}:
                validation = "N/A (no request body)"
            lines.append(
                "| "
                + " | ".join([method.upper(), path, success, validation, auth, missing, isolation, edge])
                + " |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    (ROOT / "docs" / "BACKEND_ROUTES.txt").write_text(render_inventory())
    matrix_path = ROOT / "docs" / "TEST_MATRIX.md"
    base = matrix_path.read_text().split("\n## Method-level expansion\n", 1)[0].rstrip()
    matrix_path.write_text(base + "\n\n" + render_method_matrix())
