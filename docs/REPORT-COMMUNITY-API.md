# Community visibility API report

## Visibility decision and migration

Community posts now have an explicit `visibility` field with the values `private` and `workspace`. New posts default to `private`; revision `0008_community_visibility` adds the non-null column with a server default of `private`, so existing rows remain private. The migration checks whether the column already exists, which also supports databases where earlier metadata-based table creation included the additive model field before Alembic reached revision 0008.

Authors can change their own post visibility. A caller's feed contains their own posts plus other authors' `workspace` posts. Post detail, reply listing/creation, and saving use the same visibility rule. An inaccessible private post is reported as `404`, the same as a missing post. Visible posts include `author: {display_name, role}`, `author_name`, and `author_role`; the list envelope remains `{items,total,page,page_size,pages}`. Saves are per user. No likes, reactions, unread indicators, or trending counts are returned.

The community routes permit read-only `researcher` accounts to post and reply. This does not grant case write access. Reply deletion is allowed to the reply author or an admin; another visible reader gets `403`.

## Measured HTTP authorization matrix

Observed against a freshly seeded scratch workspace on `127.0.0.1:8129`:

| Request | Status | Result |
|---|---:|---|
| Anonymous `GET /api/v1/community/posts` | 401 | Authentication required |
| Researcher reads another user's private post | 404 | `Post not found`; no existence disclosure |
| Researcher replies to or saves another user's private post | 404 | No interaction on an unreadable post |
| Advocate reads researcher workspace post | 200 | Shared post and researcher author identity returned |
| Advocate replies to researcher workspace post | 200 | Reply returned with advocate author identity |
| Researcher lists replies on that workspace post | 200 | Shared reply is visible |
| Advocate saves researcher workspace post | 200 | Saved state belongs to advocate only |
| Researcher checks `?saved=true` for advocate's saved post | 200 | Post is absent from researcher's saved list |
| Staff deletes another reader's reply | 403 | Reply author/admin restriction enforced |
| Reply author deletes their reply | 200 | `{"deleted":true}` |
| Researcher posts and replies | 200 | Read-only role can participate in Community |
| Researcher edits a case | 403 | Read-only case restriction remains |
| Invalid visibility value | 422 | Existing `{error:{code,message,details}}` validation envelope |
| Empty feed | 200 | `{"items":[],"total":0,"page":1,"page_size":20,"pages":0}` |
| `page_size=0` | 422 | Pagination validation |
| Feed page beyond last | 200 | Empty `items`, with full `total`/`pages` retained |

The reply deletion tests also cover the full three-account author/reader matrix: a non-author/non-admin receives `403`; both the researcher author and advocate author receive `200` for their own replies; an admin receives `200` when deleting a staff-authored reply. A staff user attempting to read a reply under a foreign private post receives `404`.

## Seeded feed sample

The live non-owner login (`researcher@tantara.local`) returned a mixed-author feed. This truncated sample preserves the actual envelope and author objects; the live feed also includes the advocate's explicitly shared demo post and the researcher's own private/workspace posts.

```json
{"items":[{"title":"HTTP shared fixture","visibility":"workspace","author":{"display_name":"Mira Shah","role":"researcher"},"author_name":"Mira Shah","author_role":"researcher"},{"title":"Workspace demo: Dev Patel discussion 2","visibility":"workspace","author":{"display_name":"Dev Patel","role":"staff"},"author_name":"Dev Patel","author_role":"staff"},{"title":"Workspace demo: Dev Patel discussion 1","visibility":"workspace","author":{"display_name":"Dev Patel","role":"staff"},"author_name":"Dev Patel","author_role":"staff"},{"title":"Workspace demo: Mira Shah discussion 2","visibility":"workspace","author":{"display_name":"Mira Shah","role":"researcher"},"author_name":"Mira Shah","author_role":"researcher"}],"total":7,"page":1,"page_size":4,"pages":2}
```

The IDs, timestamps, tags, body text, and `is_demo` values are omitted here for readability; the actual response retains the normal post fields and the normal list envelope.

## Tests and migration verification

Added tests:

- `test_private_posts_stay_private_and_workspace_posts_are_shared_with_author_identity`: private cross-user reads/replies/saves return 404; workspace feed, details, replies, saves, and author identity work across users.
- `test_read_only_accounts_may_post_and_reply_but_case_edits_are_forbidden`: researcher Community participation, own visibility edit, case-write 403, invalid visibility 422.
- `test_reply_delete_is_author_or_admin_only_and_uses_404_for_private_posts`: author, non-author, and admin deletion statuses.
- `test_feed_anonymous_pagination_and_empty_state_contract`: anonymous 401, empty envelope, pagination and validation edges.
- `test_0008_migrates_existing_community_posts_to_private`: exercises a pre-0008-shaped populated community table and proves the existing post survives as private.
- `test_fresh_upgrade_is_idempotent`: fresh migration path applies head, including 0008.
- `test_demo_seed_has_multpage_content_calendar_extractions_and_feed`: checks seeded cross-author posts/replies and verifies no foreign private posts enter another user's feed.
- The method-level domain CRUD matrix was updated for community's deliberate private-post 404 and read-only participation behavior.

Migration verification ran through the full suite against isolated temporary databases. Fresh upgrades apply revision `0008_community_visibility`; the existing-schema test inserts an old-shaped post before upgrading and confirms its content remains unchanged and `visibility == "private"`.

## Gates

Previous suite baseline: `TOTAL 2695 197 93%` (79 tests, from the accepted phase-five/strategy work).

Final command:

```text
RUN=$(mktemp -d); COVERAGE_FILE=/tmp/coverage-community-round8-final TANTARA_DATA_DIR="$RUN" DATABASE_URL="sqlite:///$RUN/test.db" .venv/bin/pytest -q --cov=app --cov-report=term
```

Result: `84 passed in 240.97s`.

```text
TOTAL                                2738    213    92%
```

Lint and formatting:

```text
.venv/bin/ruff check app tests ../scripts
All checks passed!
.venv/bin/ruff format --check app tests ../scripts
54 files already formatted
git diff --check
```

The requested `--cov-report=term-summary` option is not supported by this environment's installed pytest-cov; the supported `term` report above provides the TOTAL line.

## Remaining limitations

Visibility is enforced by the API schema and route predicates; the SQLite column is intentionally not constrained to the two strings at the database layer. Direct out-of-band SQL can therefore write an unsupported value, though such a value is not accepted through the API. There are no engagement-count endpoints, so the UI must not infer social counts from replies or saves.
