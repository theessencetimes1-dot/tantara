# Backend verification probes

These five scripts exercise the real HTTP API and seeded database. They are diagnostic probes, not application code. They keep their original assertions; run them from the repository root unless a command says otherwise. Do not point mutating probes at a workspace whose data you need to preserve.

| Script | Coverage | Setup and effects |
|---|---|---|
| `verify_bundles.py` | Bundle detail, JSON preview, generated/downloaded PDF page count, merge flow, range validation, and ownership. | Requires an advocate demo account, seeded cases/documents, and a generated demo bundle. Creates and mutates bundles. Pass the backend base URL. |
| `verify_drafts.py` | Draft version saves, restore history, whitespace-only save rejection, exports, and authorization. | Requires an advocate demo account and seeded case. Creates drafts and versions. Pass the backend base URL. |
| `verify_query.py` | `/query` and `/ai/ask` grounding, cited page/quote integrity, no-evidence behavior, and owner isolation. | Requires seeded indexed documents. Pass the backend base URL and the data directory containing `tantara.db`. Read-only. |
| `probe_llm_offline.py` | Honest answers when the language model is down while embeddings and retrieval remain usable. | Run against a separately started backend whose `TANTARA_LOCAL_LLM_BASE_URL` points to an unavailable local endpoint. Pass that backend URL. Read-only. |
| `probe_strategy_reliability.py` | Repeated real-model strategy generation and section completion rate; retains its 80% pass threshold. | Requires a reachable configured model and a seeded case. Optional arguments are case ID and run count. Generates strategy records and calls the model repeatedly. |

## Prepare a disposable seeded backend

```sh
mkdir -p /tmp/tantara-probes
TANTARA_DATA_DIR=/tmp/tantara-probes \
DATABASE_URL=sqlite:////tmp/tantara-probes/tantara.db \
backend/.venv/bin/python scripts/seed.py --demo

cd backend
TANTARA_DATA_DIR=/tmp/tantara-probes \
DATABASE_URL=sqlite:////tmp/tantara-probes/tantara.db \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In another terminal, from the repository root:

```sh
backend/.venv/bin/python scripts/verify_bundles.py http://127.0.0.1:8010
backend/.venv/bin/python scripts/verify_drafts.py http://127.0.0.1:8010
backend/.venv/bin/python scripts/verify_query.py http://127.0.0.1:8010 /tmp/tantara-probes
backend/.venv/bin/python scripts/probe_strategy_reliability.py http://127.0.0.1:8010
```

Run the offline-model probe only against the separately configured offline backend:

```sh
backend/.venv/bin/python scripts/probe_llm_offline.py http://127.0.0.1:8011
```

The bundle, draft, query, and strategy probes depend on their seeded data and services; a missing bundle, corpus, model, or OCR/embedding setup is a setup limitation, not a reason to relax their assertions. The strategy probe may take several minutes because it performs real model generations.
