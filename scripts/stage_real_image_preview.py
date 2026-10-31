#!/usr/bin/env python3
"""Build an isolated, LOCAL-ONLY real-photograph Catalog-Data preview.

The output has 1,500 images/products/<ASIN>.webp files and NO fixtures.
The output's media rights remain UNKNOWN; it is NOT a redistributable release
and is intentionally rejected by release bootstrap/preflight.

Never modifies the input Catalog-Data or the input candidate manifest.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from PIL import Image

EXPECTED = 1500
VERSION = "amazon-mvp1500-seed-1"


def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def secure_file(root, relative):
    path = Path(relative)
    if (path.is_absolute() or '..' in path.parts or not path.parts
            or any(p in ('', '.') for p in path.parts)):
        raise ValueError(f'UNSAFE_PATH: {relative}')
    dest = root / path
    if (dest.is_symlink() or not dest.is_file()
            or not dest.resolve().is_relative_to(root.resolve())):
        raise ValueError(f'MISSING_OR_UNSAFE_FILE: {relative}')
    return dest


def main_stage(catalog, candidate_file, output):
    catalog = Path(catalog).resolve()
    candidate_file = Path(candidate_file).resolve()
    output = Path(output).resolve()
    if not catalog.is_dir():
        raise ValueError('CATALOG_ROOT_MISSING')
    if output.is_relative_to(catalog) or output == catalog:
        raise ValueError('OUTPUT_MUST_BE_OUTSIDE_CATALOG_DATA')
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS: do not overwrite an existing preview')
    if not candidate_file.is_file():
        raise ValueError('CANDIDATE_MANIFEST_MISSING')

    old_catalog = json.loads((catalog / 'manifests/catalog_manifest.json').read_text(encoding='utf-8'))
    old_images = json.loads((catalog / 'manifests/image_manifest.json').read_text(encoding='utf-8'))
    candidate = json.loads(candidate_file.read_text(encoding='utf-8'))
    if old_catalog.get('version') != VERSION:
        raise ValueError('UNSUPPORTED_CATALOG_VERSION')
    originals = old_images.get('images', [])
    prepared = candidate.get('images', [])
    if (len(originals) != EXPECTED or len(prepared) != EXPECTED
            or len({e.get('parent_asin') for e in prepared}) != EXPECTED):
        raise ValueError('EXPECTED_1500_UNIQUE_IMAGES')
    if (candidate.get('authorized_image_count') != 0
            or candidate.get('local_preview_image_count') != EXPECTED
            or candidate.get('asset_kind') != 'AUTHENTIC_MEDIA_LOCAL_PREVIEW'):
        raise ValueError('NOT_A_LOCAL_ONLY_CANDIDATE')
    old_by_asin = {e['parent_asin']: e for e in originals}
    if len(old_by_asin) != EXPECTED:
        raise ValueError('ORIGINAL_MAPPING_NOT_UNIQUE')

    product_file = secure_file(catalog, 'data/products.jsonl')
    products = [json.loads(line) for line in product_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    product_by_asin = {p['parent_asin']: p['product']['id_proposal'] for p in products}
    if len(products) != EXPECTED or len(product_by_asin) != EXPECTED:
        raise ValueError('CATALOG_PRODUCTS_NOT_1500_UNIQUE')
    if set(product_by_asin) != set(old_by_asin):
        raise ValueError('CATALOG_IMAGES_PRODUCT_ASIN_MISMATCH')

    assets = {}
    for entry in prepared:
        asin = entry['parent_asin']
        original = old_by_asin.get(asin)
        if not original or asin not in product_by_asin:
            raise ValueError('UNKNOWN_IMAGE_ASIN: ' + asin)
        if not (entry.get('product_id_proposal') == original.get('product_id_proposal')
                == product_by_asin[asin]):
            raise ValueError('PRODUCT_UUID_CHANGED: ' + asin)
        if entry.get('source_image_url') != original.get('source_image_url'):
            raise ValueError('SOURCE_IMAGE_URL_CHANGED: ' + asin)
        relative = f'images/products/{asin}.webp'
        if entry.get('asset_path') != relative:
            raise ValueError('REAL_IMAGE_PATH_INVALID: ' + asin)
        if (entry.get('rights_status') != 'UNKNOWN'
                or entry.get('rights_evidence_reference') is not None
                or entry.get('status') != 'LOCAL_PREVIEW_ONLY'
                or entry.get('image_status') != 'AUTHENTIC_MEDIA_LOCAL_PREVIEW'):
            raise ValueError('CANDIDATE_RIGHTS_MUST_STAY_UNVERIFIED: ' + asin)
        path = secure_file(catalog, relative)
        expected = entry.get('validation') or {}
        size = path.stat().st_size
        sha = digest_file(path)
        if (sha != entry.get('sha256') or sha != expected.get('sha256')
                or size != entry.get('file_size_bytes') or size != expected.get('byte_size')
                or entry.get('content_type') != 'image/webp'
                or expected.get('content_type') != 'image/webp'):
            raise ValueError('REAL_IMAGE_CHECKSUM_OR_SIZE_MISMATCH: ' + asin)
        with Image.open(path) as image:
            image.load()
            if (image.format != 'WEBP'
                    or image.size != (entry.get('width'), entry.get('height'))
                    or image.size != (expected.get('width'), expected.get('height'))):
                raise ValueError('REAL_IMAGE_WEBP_DIMENSIONS_INVALID: ' + asin)
        assets[asin] = path

    # The candidate must correspond exactly to the supplied real image folder.
    disk_files = list((catalog / 'images/products').glob('*.webp'))
    if (len(disk_files) != EXPECTED
            or {p.stem for p in disk_files} != set(assets)):
        raise ValueError('EXTRA_OR_MISSING_REAL_PRODUCT_IMAGES')

    # Verify all metadata files BEFORE copying anything to the staged preview.
    files = old_catalog.get('file_sha256')
    if not isinstance(files, dict) or 'manifests/image_manifest.json' not in files:
        raise ValueError('CATALOG_CHECKSUM_INDEX_INVALID')
    for relative, expected_sha in files.items():
        source = secure_file(catalog, relative)
        if digest_file(source) != expected_sha:
            raise ValueError('SOURCE_CATALOG_CHECKSUM_MISMATCH: ' + relative)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.catalog-real-preview-building-', dir=output.parent))
    try:
        new_catalog = dict(old_catalog)
        new_files = dict(files)
        for relative in files:
            if relative == 'manifests/image_manifest.json':
                continue
            source = catalog / relative
            target = tmp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        (tmp / 'images/products').mkdir(parents=True, exist_ok=True)
        for asin, source in assets.items():
            shutil.copy2(source, tmp / 'images/products' / f'{asin}.webp')

        new_images = dict(candidate)
        new_images['authorized_image_count'] = 0
        new_images['local_preview_image_count'] = EXPECTED
        new_images['authentic_amazon_image_count'] = 0
        new_images['asset_kind'] = 'AUTHENTIC_MEDIA_LOCAL_PREVIEW'
        new_images['state'] = 'LOCAL_PREVIEW_ONLY_RIGHTS_UNVERIFIED'
        image_manifest = tmp / 'manifests/image_manifest.json'
        image_manifest.parent.mkdir(parents=True, exist_ok=True)
        image_manifest.write_text(json.dumps(new_images, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        new_files['manifests/image_manifest.json'] = digest_file(image_manifest)

        new_catalog.update(
            file_sha256=new_files,
            image_count=EXPECTED,
            image_rights_status='AUTHENTIC_MEDIA_LOCAL_PREVIEW',
            authentic_amazon_image_count=0,
            local_preview_image_count=EXPECTED,
            state='LOCAL_PREVIEW_ONLY_RIGHTS_UNVERIFIED',
        )
        (tmp / 'manifests/catalog_manifest.json').write_text(
            json.dumps(new_catalog, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        (tmp / 'manifests/checksums.sha256').write_text(
            ''.join(f'{new_files[name]}  {name}\n' for name in sorted(new_files)),
            encoding='utf-8',
        )
        (tmp / 'LOCAL_ONLY_DO_NOT_DISTRIBUTE.txt').write_text(
            'LOCAL TECHNICAL PREVIEW ONLY. DO NOT DISTRIBUTE. Images are real product photographs with '
            'rights_status=UNKNOWN. Do not push, publish, share, package into a Docker '
            'image, or treat this catalog as a licensed release. '
            'Release validation and Backend Bootstrap MUST fail closed.\n',
            encoding='utf-8',
        )
        os.rename(tmp, output)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    return {
        'technical_integrity': 'PASS',
        'product_count': len(products),
        'real_image_count': EXPECTED,
        'fixture_count': 0,
        'media_mode': 'AUTHENTIC_MEDIA_LOCAL_PREVIEW',
        'redistribution_rights': 'UNKNOWN',
        'release_ready': False,
        'staged_catalog': str(output),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(main_stage(args.catalog, args.candidate, args.output), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
