#!/usr/bin/env python3
"""Reseal reviewed Catalog-Data checksums; never grant or infer media rights.

Supports two *release* image modes:
  - GENERATED_FIXTURES_ONLY: images/fixtures/<ASIN>.webp
  - LICENSED_PRODUCT_IMAGES: images/products/<ASIN>.webp

Rights evidence must be reviewed independently. This script only checks that
manifest assertions are internally consistent; it does not grant a license.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASIN = re.compile(r"^[A-Z0-9]{10}$")
EXPECTED_COUNT = 1500

IMAGE_MODES = {
    "GENERATED_FIXTURES_ONLY": {
        "directory": "fixtures",
        "rights_status": "GENERATED_ORIGINAL_FIXTURE",
    },
    "LICENSED_PRODUCT_IMAGES": {
        "directory": "products",
        "rights_status": "LICENSED_FOR_REDISTRIBUTION",
    },
}


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _safe_file(root, relative):
    """Return an existing regular file confined to the package directory."""
    if not isinstance(relative, str) or not relative:
        raise ValueError("Missing package-relative file path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe package path: {relative}")
    path = root / candidate
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or symlinked package file: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Package file escapes root: {relative}")
    return path


def _atomic_write(path, contents):
    """Replace a metadata file via an adjacent temporary file."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False
        ) as output:
            temporary_path = Path(output.name)
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run(root=ROOT, acknowledge=False, dry_run=False):
    """Validate an already-reviewed release and reseal tracked file hashes.

    The existing image manifest must already contain correct per-image hashes,
    dimensions, product IDs, and actual rights evidence. Unknown rights fail.
    """
    if not acknowledge and not dry_run:
        raise ValueError("Explicit --acknowledge-reviewed-changes required")

    root = Path(root).resolve()
    manifest_path = root / "manifests/catalog_manifest.json"
    image_manifest_path = root / "manifests/image_manifest.json"
    manifest = _load_json(manifest_path)
    image_manifest = _load_json(image_manifest_path)

    if manifest.get("version") != "amazon-mvp1500-seed-1":
        raise ValueError("Unsupported catalog manifest version")
    if manifest.get("data_approval_status") != "APPROVED":
        raise ValueError("Development data approval is not recorded")

    mode = manifest.get("image_rights_status")
    image_policy = IMAGE_MODES.get(mode)
    if image_policy is None:
        raise ValueError(f"Unsupported or unapproved image release mode: {mode}")

    products = _load_jsonl(root / "data/products.jsonl")
    variants = _load_jsonl(root / "data/variants.jsonl")
    specs = _load_jsonl(root / "data/specifications.jsonl")
    images = image_manifest.get("images")
    if not isinstance(images, list) or any(
        len(rows) != EXPECTED_COUNT for rows in (products, variants, specs, images)
    ):
        raise ValueError("Expected exactly 1,500 Products, Variants, Specs and Images")

    ids = [product.get("parent_asin") for product in products]
    expected_ids = set(ids)
    if (len(expected_ids) != EXPECTED_COUNT
            or any(not isinstance(asin, str) or not ASIN.fullmatch(asin) for asin in ids)
            or {row.get("parent_asin") for row in variants} != expected_ids
            or {row.get("parent_asin") for row in specs} != expected_ids
            or {row.get("parent_asin") for row in images} != expected_ids):
        raise ValueError("Catalog ASIN identities are missing, duplicated, or inconsistent")

    product_uuids = {
        product["parent_asin"]: product["product"]["id_proposal"]
        for product in products
    }
    referenced_paths = set()
    digest_sources = {}
    total_image_bytes = 0

    for image in images:
        asin = image["parent_asin"]
        relative = image.get("asset_path")
        expected_relative = f"images/{image_policy['directory']}/{asin}.webp"
        if relative != expected_relative:
            raise ValueError(f"Unexpected image path for {asin}: {relative}")
        if relative in referenced_paths:
            raise ValueError(f"Image file referenced more than once: {relative}")
        referenced_paths.add(relative)
        if image.get("product_id_proposal") != product_uuids[asin]:
            raise ValueError(f"Product UUID does not match image: {asin}")

        if image.get("rights_status") != image_policy["rights_status"]:
            raise ValueError(f"Image release rights not established: {asin}")
        if image.get("status") != "VALIDATED_AUTHORIZED_ASSET":
            raise ValueError(f"Image is not marked as release-authorized: {asin}")
        evidence = image.get("rights_evidence_reference")
        if mode == "GENERATED_FIXTURES_ONLY":
            if (evidence != "scripts/generate_fixture_images.py"
                    or image.get("image_status") != "GENERATED_FIXTURE"):
                raise ValueError(f"Fixture generator evidence invalid: {asin}")
        else:
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"Missing redistribution rights evidence reference: {asin}")
            license_path = Path(evidence)
            if (license_path.is_absolute() or '..' in license_path.parts
                    or license_path.parts[:2] != ('manifests', 'licenses')
                    or len(license_path.parts) < 3):
                raise ValueError(f"Invalid redistribution rights evidence path: {asin}")
            _safe_file(root, evidence)
            if evidence not in manifest.get('file_sha256', {}):
                raise ValueError(f"Redistribution evidence must be checksum-indexed: {asin}")

        asset = _safe_file(root, relative)
        data = asset.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        validation = image.get("validation")
        if not isinstance(validation, dict):
            raise ValueError(f"Missing image validation record: {asin}")
        if (image.get("sha256") != digest or validation.get("sha256") != digest
                or image.get("file_size_bytes") != len(data)
                or validation.get("byte_size") != len(data)):
            raise ValueError(f"Image checksum or byte size differs from reviewed manifest: {asin}")
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"Unfetched Git LFS pointer: {asin}")
        if image.get("content_type") != "image/webp" or validation.get("content_type") != "image/webp":
            raise ValueError(f"Image content type mismatch: {asin}")
        try:
            with Image.open(asset) as decoded:
                decoded.load()
                dimensions = (decoded.width, decoded.height)
                if decoded.format != "WEBP" or dimensions != (
                    image.get("width"), image.get("height")
                ) or dimensions != (
                    validation.get("width"), validation.get("height")
                ):
                    raise ValueError("Image dimensions or format mismatch")
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid WebP image {asin}: {exc}") from exc

        source_url = image.get("source_image_url")
        if digest in digest_sources and (
            not source_url or source_url != digest_sources[digest]
        ):
            raise ValueError(f"Unexpected duplicate image content for {asin}")
        digest_sources[digest] = source_url
        total_image_bytes += len(data)

    # A release package must not also contain unreferenced private previews,
    # old fixture images, or arbitrary assets, regardless of Git ignore rules.
    images_directory = root / "images"
    unexpected = sorted(
        item.relative_to(root).as_posix()
        for item in images_directory.rglob("*")
        if (item.is_file() or item.is_symlink())
        and item.relative_to(root).as_posix() not in referenced_paths
    ) if images_directory.exists() else []
    if unexpected:
        raise ValueError(
            f"Unreferenced image assets ({len(unexpected)}): "
            + ", ".join(unexpected[:3])
            + (" ..." if len(unexpected) > 3 else "")
        )

    if image_manifest.get("authorized_image_count") != EXPECTED_COUNT:
        raise ValueError("Image manifest's authorized count is not 1,500")
    expected_kind = (
        "LICENSED_PRODUCT_IMAGE" if mode == "LICENSED_PRODUCT_IMAGES"
        else "GENERATED_ILLUSTRATIVE_FIXTURE"
    )
    if image_manifest.get("asset_kind") != expected_kind:
        raise ValueError("Image manifest asset kind does not match release mode")
    if manifest.get("image_count") != EXPECTED_COUNT:
        raise ValueError("Catalog manifest's image count is not 1,500")
    if manifest.get("local_preview_image_count") != 0:
        raise ValueError("Local-preview images cannot be part of this release")
    expected_authentic_count = EXPECTED_COUNT if mode == "LICENSED_PRODUCT_IMAGES" else 0
    if manifest.get("authentic_amazon_image_count") != expected_authentic_count:
        raise ValueError("Catalog image-type accounting is inconsistent")
    if image_manifest.get("authentic_amazon_image_count") != expected_authentic_count:
        raise ValueError("Image manifest image-type accounting is inconsistent")

    # Only recalculate hashes for explicitly indexed package files. Do not
    # rewrite approvals, image rights, image identities, or image metadata.
    indexed = manifest.get("file_sha256")
    if not isinstance(indexed, dict) or "manifests/image_manifest.json" not in indexed:
        raise ValueError("Invalid file checksum index")
    new_hashes = {}
    for name in indexed:
        path = _safe_file(root, name)
        new_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    new_manifest = dict(manifest)
    new_manifest["file_sha256"] = new_hashes
    manifest_text = json.dumps(new_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    checksum_text = "".join(
        f"{new_hashes[name]}  {name}\n" for name in sorted(new_hashes)
    )

    if not dry_run:
        _atomic_write(manifest_path, manifest_text)
        _atomic_write(root / "manifests/checksums.sha256", checksum_text)

    return {
        "mode": "dry-run" if dry_run else "resealed",
        "file_count": len(new_hashes),
        "image_count": EXPECTED_COUNT,
        "image_bytes": total_image_bytes,
        "data_approval_status": manifest.get("data_approval_status"),
        "image_rights_status": mode,
        "rights_granted_by_script": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--acknowledge-reviewed-changes", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing manifests")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root, args.acknowledge_reviewed_changes, args.dry_run), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as failure:
        print(str(failure), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
