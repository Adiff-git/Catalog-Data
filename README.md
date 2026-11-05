# Catalog data

This repository contains the 1,500-product DRAFT catalog seed and its 1,500 product images.

## Files for import

- `data/products.jsonl`, `data/variants.jsonl`, `data/specifications.jsonl`: catalog records and stable IDs.
- `data/category_mapping.json`: category IDs and paths.
- `data/approvals/amazon_import_approved_1500.csv`: approved SKU and demo price values for the full import.
- `images/product/<ASIN>.webp`: one product image per ASIN.
- `manifests/catalog_manifest.json`, `manifests/image_manifest.json`, `manifests/checksums.sha256`: identity, integrity, and image inventory.
- `scripts/validate_catalog.py`: local package validation used by the sibling Backend image importer.

After cloning, install Python 3 and Pillow, then run `python3 scripts/validate_catalog.py` from this repository. All 1,500 images are ordinary Git files; Git LFS is not required.

The full data import uses the sibling Backend-SWE `tools/catalog-import/amazon_import.py` with this repository as `--seed`, `data/approvals/amazon_import_approved_1500.csv` as `--approvals`, and `data/category_mapping.json` as `--categories`. The Backend importer needs its own dependencies and target database configuration. This seed supports the full 1,500-product import; stage 100 and 1,000 lists are not included.

`package_valid=true` and `ready_for_bootstrap=true` mean local bytes and mappings are consistent. The sibling Backend image importer reads `images/product/` and can upload them through its existing authenticated API when a target and credentials are supplied.
