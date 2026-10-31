#!/usr/bin/env python3
"""Validate portable catalog package; no Dataset or database dependency."""
from collections import Counter
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ASIN=re.compile(r'^[A-Z0-9]{10}$')
SKU=re.compile(r'^DEMO-AMZ-[A-Z0-9]{10}$')
HEX64=re.compile(r'^[0-9a-f]{64}$')

def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:return [json.loads(x) for x in stream if x.strip()]

def validate(root=ROOT):
    root=Path(root);issues=[]
    manifest=json.loads((root/'manifests/catalog_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version')!='amazon-mvp1500-seed-1':issues.append('UNSUPPORTED_VERSION')
    file_sizes={}
    for relative,expected in manifest.get('file_sha256',{}).items():
        path=root/relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts:issues.append('UNSAFE_MANIFEST_PATH:'+relative);continue
        if not path.is_file() or path.is_symlink():issues.append('MISSING_FILE:'+relative);continue
        data=path.read_bytes();file_sizes[relative]=len(data)
        if hashlib.sha256(data).hexdigest()!=expected:issues.append('CHECKSUM_MISMATCH:'+relative)
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            issues.append('GIT_LFS_POINTER_NOT_FETCHED:'+relative)
    expected_checksums=''.join(f'{manifest["file_sha256"][name]}  {name}\n' for name in sorted(manifest.get('file_sha256',{})))
    if (root/'manifests/checksums.sha256').read_text(encoding='utf-8')!=expected_checksums:
        issues.append('CHECKSUM_LIST_MISMATCH')
    products=read_jsonl(root/'data/products.jsonl');specs=read_jsonl(root/'data/specifications.jsonl');variants=read_jsonl(root/'data/variants.jsonl')
    if len(products)!=1500 or len(products)!=len(specs) or len(products)!=len(variants):issues.append('CATALOG_COUNT_MISMATCH')
    ids=set();skus=set();product_uuids=set();variant_uuids=set();distribution=Counter()
    for product,spec,variant in zip(products,specs,variants):
        asin=product.get('parent_asin')
        if not isinstance(asin,str) or not ASIN.fullmatch(asin) or asin in ids:issues.append('INVALID_OR_DUPLICATE_ASIN')
        ids.add(asin)
        if spec.get('parent_asin')!=asin or variant.get('parent_asin')!=asin:issues.append('IDENTITY_MISMATCH')
        p=product.get('product',{});v=variant.get('variant',{})
        for value,seen,label in ((p.get('id_proposal'),product_uuids,'PRODUCT'),(v.get('id_proposal'),variant_uuids,'VARIANT')):
            try:
                parsed=str(uuid.UUID(value))
                if parsed in seen:issues.append('DUPLICATE_'+label+'_UUID')
                seen.add(parsed)
            except (ValueError,TypeError):issues.append('INVALID_'+label+'_UUID')
        if p.get('status')!='DRAFT' or product.get('disposition')!='BLOCKED':issues.append('UNEXPECTED_APPROVAL_OR_PUBLICATION')
        if v.get('product_id_proposal')!=p.get('id_proposal') or not v.get('id_proposal'):issues.append('VARIANT_RELATIONSHIP_MISMATCH')
        if v.get('option_combination_proposal')!={}:issues.append('UNEXPECTED_VARIANT_OPTIONS')
        sku=v.get('sku_proposal')
        if not isinstance(sku,str) or not SKU.fullmatch(sku) or sku.casefold() in skus:issues.append('INVALID_OR_DUPLICATE_SKU')
        skus.add(sku.casefold())
        doc=spec.get('technical_specifications')
        if not isinstance(doc,dict) or set(doc)!={'schema_version','values'} or doc.get('schema_version')!=1 or not isinstance(doc.get('values'),dict):issues.append('INVALID_SPEC_DOCUMENT')
        distribution[p.get('category_label')]+=1
    if dict(sorted(distribution.items()))!=manifest.get('category_distribution'):issues.append('CATEGORY_DISTRIBUTION_MISMATCH')
    categories=json.loads((root/'data/category_mapping.json').read_text(encoding='utf-8')).get('categories',[])
    by_label={x.get('source_category'):x for x in categories}
    if len(categories)!=10 or set(by_label)!=(set(distribution)|{'Electronics'}):issues.append('CATEGORY_MAPPING_ACCOUNTING_MISMATCH')
    for label,row in by_label.items():
        expected_path=['Electronics'] if label=='Electronics' else ['Electronics',label]
        if row.get('approval')!='APPROVED' or row.get('path')!=expected_path:issues.append('CATEGORY_POLICY_INVALID:'+str(label))
        try:uuid.UUID(row['category_uuid'])
        except (ValueError,TypeError,KeyError):issues.append('CATEGORY_UUID_INVALID:'+str(label))
        if row.get('parent_uuid')!=(None if label=='Electronics' else by_label.get('Electronics',{}).get('category_uuid')):
            issues.append('CATEGORY_PARENT_INVALID:'+str(label))
    image_manifest=json.loads((root/'manifests/image_manifest.json').read_text(encoding='utf-8'))
    images=image_manifest.get('images',[])
    if len(images)!=1500 or {x.get('parent_asin') for x in images}!=ids:issues.append('IMAGE_MANIFEST_MAPPING_MISMATCH')
    actual_assets=0;asset_bytes=0;asset_digests=set()
    referenced_assets=set()
    for image in images:
        product=next((p for p in products if p['parent_asin']==image.get('parent_asin')),None)
        if not product or image.get('product_id_proposal')!=product['product']['id_proposal']:
            issues.append('IMAGE_PRODUCT_UUID_MISMATCH')
        relative=image.get('asset_path')
        if not relative:continue
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts or path.parts[0]!='images':issues.append('UNSAFE_IMAGE_PATH');continue
        referenced_assets.add(path.as_posix())
        asset=root/path
        if not asset.is_file() or asset.is_symlink():issues.append('MISSING_IMAGE_ASSET:'+relative);continue
        data=asset.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if digest!=image.get('validation',{}).get('sha256'):issues.append('IMAGE_CHECKSUM_MISMATCH:'+relative)
        if image.get('rights_status')!='GENERATED_ORIGINAL_FIXTURE' or image.get('rights_evidence_reference')!='scripts/generate_fixture_images.py' or not relative.startswith('images/fixtures/'):
            issues.append('IMAGE_RIGHTS_UNSUPPORTED:'+relative)
        try:
            with Image.open(asset) as decoded:
                decoded.load()
                if decoded.format!='WEBP' or decoded.size!=(image.get('width'),image.get('height')):
                    issues.append('INVALID_IMAGE_DIMENSIONS_OR_FORMAT:'+relative)
        except Exception:issues.append('INVALID_IMAGE:'+relative)
        if len(data)!=image.get('file_size_bytes'):issues.append('IMAGE_SIZE_MISMATCH:'+relative)
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):issues.append('GIT_LFS_POINTER_NOT_FETCHED:'+relative)
        if digest in asset_digests:issues.append('DUPLICATE_IMAGE_BYTES:'+relative)
        asset_digests.add(digest);actual_assets+=1;asset_bytes+=len(data)
    for asset in (root/'images').rglob('*') if (root/'images').exists() else ():
        if asset.is_file() and asset.relative_to(root).as_posix() not in referenced_assets:
            issues.append('UNREFERENCED_IMAGE_ASSET:'+asset.relative_to(root).as_posix())
    if (root/'.local-image-cache').exists():issues.append('LOCAL_PREVIEW_CACHE_IN_DISTRIBUTABLE_PACKAGE')
    if actual_assets!=manifest.get('image_count'):issues.append('IMAGE_COUNT_MISMATCH')
    approval_path=root/'data/approvals/amazon_import_approved_1500.csv'
    with approval_path.open(encoding='utf-8',newline='') as stream:
        approvals=list(csv.DictReader(stream))
    if len(approvals)!=1500 or {x['parent_asin'] for x in approvals}!=ids:issues.append('APPROVAL_ACCOUNTING_MISMATCH')
    approved={x['parent_asin']:x for x in approvals}
    variants_by_asin={x['parent_asin']:x for x in variants}
    for product in products:
        asin=product['parent_asin'];row=approved.get(asin)
        if not row:continue
        if any(row.get(k)!='APPROVED' for k in ('category_approval','sku_policy_approval','variant_approval','price_approval','import_approval')):
            issues.append('MISSING_IMPORT_APPROVAL:'+asin)
        if row.get('publication_approval')!='PENDING_APPROVAL':issues.append('UNEXPECTED_PUBLICATION_APPROVAL:'+asin)
        if row.get('approved_sku')!=variants_by_asin[asin]['variant']['sku_proposal']:
            issues.append('APPROVED_SKU_MISMATCH:'+asin)
        try:
            from decimal import Decimal
            amount=Decimal(row['approved_selling_price_vnd'])
            if not amount.is_finite() or amount<=0 or amount!=amount.to_integral_value():raise ValueError()
        except Exception:issues.append('APPROVED_PRICE_INVALID:'+asin)
        if row.get('approved_category_uuid') and row['approved_category_uuid']!=by_label[product['product']['category_label']]['category_uuid']:
            issues.append('APPROVED_CATEGORY_MISMATCH:'+asin)
    suspicious=[]
    for path in root.rglob('*'):
        if not path.is_file() or '.git' in path.parts:continue
        if any(part in {'node_modules','.venv','__pycache__'} for part in path.parts):continue
        if path.suffix.lower() in {'.env','.key','.pem','.p12','.sqlite','.db','.parquet','.dump'}:
            suspicious.append(str(path.relative_to(root)))
        if path.stat().st_size>100*1024*1024:suspicious.append(str(path.relative_to(root))+':OVER_100_MIB')
        if path.resolve()!=Path(__file__).resolve() and path.suffix.lower() in {'.json','.jsonl','.csv','.md','.txt','.sh','.py'} and path.stat().st_size<=30*1024*1024:
            data=path.read_bytes()
            if (b'-----BEGIN PRIVATE KEY-----' in data or re.search(rb'AKIA[0-9A-Z]{16}',data)
                    or re.search(rb'postgres(?:ql)?://[^\s:/@]+:[^\s@]+@',data)):
                suspicious.append(str(path.relative_to(root))+':POSSIBLE_SECRET')
    issues.extend('UNEXPECTED_OR_LARGE_FILE:'+x for x in suspicious)
    return {'version':'catalog-package-validation-1','product_count':len(products),'variant_count':len(variants),
            'image_count':actual_assets,'image_bytes':asset_bytes,'metadata_bytes':sum(file_sizes.values()),
            'git_lfs_available':bool(shutil.which('git-lfs')),'issues':sorted(set(issues)),
            'package_valid':not issues,'ready_for_bootstrap':not issues and manifest.get('data_approval_status')=='APPROVED'
                   and manifest.get('image_rights_status')=='GENERATED_FIXTURES_ONLY' and actual_assets==1500,
            'manifest_state':manifest.get('state')}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    try:
        report=validate(args.root);print(json.dumps(report,indent=2,sort_keys=True))
        sys.exit(0 if report['package_valid'] else 2)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as failure:
        print(json.dumps({'error':str(failure)}),file=sys.stderr);sys.exit(2)
