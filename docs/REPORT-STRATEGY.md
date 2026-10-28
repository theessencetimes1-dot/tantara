# Strategy Advisor report

## Mode and response contract

`POST /api/v1/cases/{cid}/strategy/generate` now returns one of four modes:

- `model_generated`: a valid structured response was returned by the configured local model and every non-empty assertion cites a chunk from this user's case evidence. `model` identifies that model.
- `template`: evidence exists, but the model did not return a complete, valid, fully cited strategy. The response contains only retrieved excerpts and says they were assembled without a model. `model` is `null`; `key_issues` and `counterarguments` are empty.
- `no_evidence`: retrieval returned no indexed case evidence, so no model call is made. `model` is `null`.
- `model_unavailable`: the local call failed. The response contains only retrieved excerpts, explicitly says they were assembled without a model, and has `model: null`, empty `key_issues`, and empty `counterarguments`.

All modes include `generated_at`, `status`, `citations`, `assertion_citations`, `generation_note`, and `manually_edited`. Citation records include document ID, document title, chunk ID, and source page. The established strategy fields remain in place. GET returns persisted generation mode, timestamp, citations, and content. PUT preserves that mode as generation history, clears model attribution and assertion-level citation mappings for the edited text, and sets `manually_edited: true` with an owner-edit note.

## Prompt and grounding

Strategy generation uses the existing `llm_answer` local OpenAI-compatible call and the existing owner-scoped retrieval service. The request asks for JSON sections for case theory, issues, legal arguments, counterarguments, evidence gaps, and a verification plan. Each section must identify exact chunk IDs. JSON response mode and disabled model thinking reduce unstructured reasoning output. The response validator resolves each cited chunk against the retrieved hit set, verifies any cited page suffix, and rejects the entire model response if an assertion is uncited, cites an unknown page/chunk, or a required section is missing. Those checks reuse the retrieved chunk citation records rather than creating a separate citation lookup path.

The strategy-specific user prompt is:

```text
Return JSON only with keys case_theory, key_issues, legal_arguments, counterarguments, evidence_gaps, strategy_plan. Each value is an object {"text":"...", "citations":["chunk-id"]}. Use only retrieved excerpts. Give one concise, evidence-bounded statement per section. Every non-empty text must cite one or more exact chunk IDs from the excerpts; citations cannot be empty. For counterarguments, give a question counsel should test, not an alleged fact. For evidence gaps, state what the excerpts do not establish and cite the reviewed excerpts. Make the plan a concrete verification step and cite its source. Do not invent facts, law, rules, or citations. CASE: {case title}
```

The shared grounding helper adds the query header and includes each retrieved excerpt as `[chunk_id p.N] snippet`. The exact chunk IDs are validated against hits already scoped to the authenticated owner's case, and the citation object attached to each accepted claim includes the indexed document title and page.

## Verification

Coverage before this change: `TOTAL 2587 183 93%` (76 tests, 121.08s).

Final full-suite command (run from `backend/` with its own scratch data/database):

```text
pytest -q --cov=app --cov-report=term
79 passed in 177.25s (0:02:57)
TOTAL 2695 197 93%
```

Ruff gates: `ruff check .` passed; `ruff format --check .` passed (`60 files already formatted`). Final strategy-focused tests: `11 passed in 32.01s`.

The focused strategy/degradation tests are:

- `test_strategy_local_model_generates_cited_assertions_and_persists_mode`
- `test_strategy_unreachable_model_is_excerpt_only_and_scoped`
- `test_strategy_without_indexed_evidence_has_distinct_no_evidence_mode`
- `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` (extended to check Strategy's outage mode)
- `test_strategy_evidence_autofill_skip_and_existing_preference` (preserves existing GET/PUT behavior)

These cover a local OpenAI-compatible endpoint, a closed loopback port, empty evidence, citation page and owner checks, anonymous 401, the demo `researcher@tantara.local` account's cross-owner 404, GET persistence, and PUT's manual-edit marker.

### Live model response (seeded workspace, truncated)

Request: `POST /api/v1/cases/8926ad33-3982-4d1e-b132-e5afd09ebda6/strategy/generate`, authenticated as `advocate@tantara.local`, with the configured MiniCPM endpoint reachable.

```json
{
  "case_theory": "The case involves an arbitration agreement under Section 7 of the Arbitration and Conciliation Act, 1996, with disputes to be submitted to arbitration seated in Mumbai, India.",
  "key_issues": ["The key issue is the validity and applicability of the arbitration agreement and its seat in Mumbai, India."],
  "counterarguments": ["Counsel should test whether the arbitration agreement's terms are fully enforceable given the location of arbitration in Mumbai, India."],
  "evidence_gaps": ["The excerpts do not establish the scope of the arbitration agreement or the parties' intent beyond the stated location of arbitration."],
  "legal_arguments": [{
    "statement": "The parties agreed to submit disputes to arbitration under Section 7 of the Arbitration and Conciliation Act, 1996, as stated in the arbitration agreement.",
    "support": [{"document_title": "Arbitration Agreement", "page_number": 2, "chunk_id": "15ed68ed-854a-41cd-93ed-ac5dec12a862"}]
  }],
  "strategy_plan": "Verify the enforceability of the arbitration agreement under Section 7 of the Arbitration and Conciliation Act, 1996, by reviewing the arbitration agreement terms.",
  "status": "model_generated",
  "model": {"provider": "local", "model": "MiniCPM5-2B"},
  "assertion_citations": ["... each generated statement maps to owner-scoped document/page citations ..."]
}
```

### Unreachable model response (seeded workspace, truncated)

The same request after setting the user's AI base URL to `http://127.0.0.1:9/v1` returned:

```json
{
  "case_theory": "",
  "key_issues": [],
  "legal_arguments": [{
    "statement": "Source excerpt: Arbitration Agreement — Page 3\\nArbitration agreement",
    "support": [{"document_title": "Arbitration Agreement", "page_number": 3, "chunk_id": "71f5ceaf-ab90-47f9-aa05-4bdbca4328ad"}]
  }],
  "counterarguments": [],
  "evidence_gaps": ["Retrieved excerpts do not address opposing evidence or governing law."],
  "strategy_plan": "",
  "status": "model_unavailable",
  "model": null,
  "generation_note": "The configured model is unavailable; the content below is source excerpts assembled without a model."
}
```

The live route returned citations for the rest of the retrieved excerpts too; they are omitted above for readability.

## Remaining limits

The live check proves the configured MiniCPM endpoint can generate one fully cited strategy for this demo case; it does not establish legal correctness or behavior across every case type. The model is nondeterministic. If it returns malformed JSON, omits a strategy section, or cites a chunk/page outside the retrieved owner-scoped evidence, the API deliberately returns `template` excerpts and does not attribute them to the model. Counsel must review generated analysis before use.
