#!/usr/bin/env python3
"""Inventory local authentic WebPs without granting media redistribution rights.

Creates a LOCAL-ONLY, NON-RELEASE manifest candidate outside Catalog-Data.
This file MUST NOT replace manifests/image_manifest.json until actual rights
are independently documented and the release/package workflow is reviewed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASIN = re.compile(r"^[A-Z0-9]{10}$")


def build_candidate(root, images_dir, output):
    root = Path(root).resolve()
    images_dir = Path(images_dir).resolve()
    output = Path(output).resolve()
    if output.is_relative_to(root):
        raise ValueError("Local preview report must be written OUTSIDE Catalog-Data")
    if not images_dir.is_dir():
        raise ValueError(f"Image directory not found: {images_dir}")
    source = json.loads((root / "manifests/image_manifest.json").read_text(encoding="utf-8"))
    rows = source["images"]
    asins = {row["parent_asin"] for row in rows}
    files = list(images_dir.glob("*.webp"))
    actual = {path.stem for path in files}
    if (len(rows) != 1500 or len(asins) != 1500 or len(files) != 1500
            or actual != asins or any(not ASIN.fullmatch(asin) for asin in asins)):
        raise ValueError(
            f"Expected exactly 1,500 source mappings and WebPs; "
            f"missing={len(asins-actual)} extra={len(actual-asins)}"
        )

    candidate = dict(source)
    candidate["images"] = []
    for original in rows:
        row = dict(original)
        asin = row["parent_asin"]
        file_path = images_dir / f"{asin}.webp"
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError(f"Missing or symlink image: {asin}")
        data = file_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        with Image.open(file_path) as image:
            image.load()
            if image.format != "WEBP":
                raise ValueError(f"Not a WebP image: {asin}")
            width, height = image.size
        row.update({
            "asset_path": f"images/products/{asin}.webp",
            "file_size_bytes": len(data),
            "width": width,
            "height": height,
            "sha256": digest,
            "content_type": "image/webp",
            "validation": {
                "sha256": digest, "byte_size": len(data),
                "width": width, "height": height,
                "content_type": "image/webp",
            },
            "image_status": "AUTHENTIC_MEDIA_LOCAL_PREVIEW",
            "rights_status": "UNKNOWN",
            "rights_evidence_reference": None,
            "status": "LOCAL_PREVIEW_ONLY",
            "local_image_path": None,
        })
        candidate["images"].append(row)
    candidate.update({
        "asset_kind": "AUTHENTIC_MEDIA_LOCAL_PREVIEW",
        "authorized_image_count": 0,
        "authentic_amazon_image_count": 0,
        "local_preview_image_count": len(rows),
        "state": "LOCAL_PREVIEW_ONLY_RIGHTS_UNVERIFIED",
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "images_checked": len(rows),
        "rights_status": "UNKNOWN",
        "release_ready": False,
        "output": str(output),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        print(json.dumps(build_candidate(arguments.root, arguments.images_dir, arguments.output), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
