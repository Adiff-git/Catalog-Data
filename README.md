# Catalog-Data development seed

This repository packages the approved 1,500-Product MVP catalog, one Variant per Product, technical specifications, source ASIN provenance, and category-level positive VND **demo prices**. Every Product is DRAFT. The images under `images/fixtures/` are original, ASIN-labeled **illustrative fixtures**; they are not Amazon product photographs.

The original Amazon-derived local preview cache is outside this repository. Its media rights remain UNKNOWN. It is not included here or authorized for redistribution. `manifests/image_manifest.json` records each fixture's Product UUID, relative path, checksum, dimensions, and fixture rights status. `manifests/catalog_manifest.json` records package state and file checksums.

## Validate after clone

Install Python 3 and Pillow, then run:

```bash
python3 scripts/validate_catalog.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

The validator needs only this checkout. It checks Product, Variant, specification, approval, Category, and image identities; image bytes; checksums; unsafe paths; and likely secrets. The fixture set is about 3.7 MB and uses ordinary Git. Git LFS is not required. `python3 scripts/reseal_catalog.py --acknowledge-reviewed-changes` is reserved for intentional reviewed edits; it does not grant rights or import approval.

## Import contract

Clone `Backend-SWE` and this repository as siblings from their actual verified GitHub destinations. `data/products.jsonl`, `data/variants.jsonl`, and `data/specifications.jsonl` are the portable source of truth. `data/category_mapping.json` supplies deterministic UUIDs for an Electronics root and nine children. It does not rely on the current development database. The approved CSV leaves `approved_category_uuid` blank so the Backend importer resolves the approved Category path from that mapping; all 1,500 import, SKU, Variant, and price approvals are recorded in the CSV. No original Amazon Parquet data or owner-machine path is needed.

Backend-SWE's `tools/catalog-import/amazon_import.py` loads the catalog using `--seed` pointing to this clone, `--approvals data/approvals/amazon_import_approved_1500.csv`, and `--categories data/category_mapping.json`, after verifying compatible PostgreSQL 17 with Flyway V1–V10. On an existing exact seed it is a no-op. Environment-specific target credentials and authorization belong outside this repository. The local fixture image importer is `tools/catalog-import/amazon_image_import.py --fixture-mode`; it uses the Backend media upload API, LocalStack configuration, and a local checkpoint. It creates one independent primary ProductImage per Product and can resume or replay.

The future Phase 5 Docker bootstrap will automate fresh-database and LocalStack initialization and import order. Phase 6 will verify the complete fresh-clone workflow. Current package validation does not claim those phases are done. Product listing APIs may not show this seed because Products remain DRAFT.

Authentic Amazon-derived photos require separate documented storage and redistribution rights before release packaging or upload. Do not copy `Dataset/.local-image-cache/` into this repository.
