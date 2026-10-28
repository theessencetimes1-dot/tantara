# Prototype data reconciliation

Revision `0004_reconcile_legacy` exports every remaining `*_legacy_0002` table as
`backend/data/archive/legacy_export.json` (or the configured `TANTARA_DATA_DIR`
archive directory), then drops those archive tables. Export runs before any drop,
and each exported table retains all row fields. Datetimes are ISO formatted and
binary values are hex encoded. The selected policy avoids silently discarding
untyped JSON payloads that cannot safely be mapped to typed domain records.

The revision also creates `rate_buckets` for SQLite-backed shared request limits.
On the fixture prototype database used by `test_prototype_json_rows_are_exported_and_user_kept`,
one legacy case row was exported from `cases_legacy_0002`; typed `cases` remained
empty, the users row remained intact, and the archive table was removed. Empty
tables are included in the export with zero rows. The test inspects the JSON and
the upgraded SQLite schema after a real Alembic upgrade.

Export counts are environment-specific. For a workspace, inspect the array
lengths under `tables` in `legacy_export.json`; do not treat the fixture count as
the user's production count. Keep the exported file in the backup set before
removing it.

Revision `0005_bundle_page_ranges` adds nullable `page_start` and `page_end`
columns to `bundle_items`; these are inclusive source-document page numbers.
Existing bundle items with null values continue to include the complete source
document.
