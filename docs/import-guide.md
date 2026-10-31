# Portable catalog import contract

The portable seed consists of `data/products.jsonl`, `data/variants.jsonl`, `data/specifications.jsonl`, `data/approvals/amazon_import_approved_1500.csv`, and `data/category_mapping.json`. Its manifest and checksums are under `manifests/`. Run `python3 scripts/validate_catalog.py` from this checkout before any import.

The Backend importer resolves Category UUIDs from the approved Electronics paths. They are deterministic and created in a compatible database when absent; a same-ID/different-parent conflict blocks import. Product and Variant UUIDs are stable in the JSONL. The approved CSV supplies internal demo SKU and positive VND price. All Product statuses remain DRAFT.

Use the sibling Backend-SWE repository's documented target-specific importer flags and credentials, supplied privately at runtime. The database must be PostgreSQL 17 with exact Flyway V1–V10. No Dataset directory, Parquet source, existing database rows, LocalStack objects, or absolute owner-machine paths are required to validate this package. Phase 5 will provide the one-command fresh-database bootstrap and Phase 6 will verify it from new clones.
