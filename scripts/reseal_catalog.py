#!/usr/bin/env python3
"""Refresh deterministic file checksums after reviewed edits; never grants approval."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def run(root=ROOT,acknowledge=False):
    if not acknowledge:raise ValueError('Explicit --acknowledge-reviewed-changes required')
    root=Path(root);path=root/'manifests/catalog_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('version')!='amazon-mvp1500-seed-1':raise ValueError('Unsupported manifest version')
    files=manifest.get('file_sha256',{})
    for name in files:
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or not (root/relative).is_file():raise ValueError('Missing or unsafe package file')
        files[name]=hashlib.sha256((root/relative).read_bytes()).hexdigest()
    products=[json.loads(x) for x in (root/'data/products.jsonl').read_text().splitlines() if x]
    variants=[json.loads(x) for x in (root/'data/variants.jsonl').read_text().splitlines() if x]
    specs=[json.loads(x) for x in (root/'data/specifications.jsonl').read_text().splitlines() if x]
    images=json.loads((root/'manifests/image_manifest.json').read_text(encoding='utf-8'))['images']
    if any(len(rows)!=1500 for rows in (products,variants,specs,images)):
        raise ValueError('Catalog or image accounting invalid')
    ids={p['parent_asin'] for p in products}
    if len(ids)!=1500 or {v['parent_asin'] for v in variants}!=ids or {s['parent_asin'] for s in specs}!=ids or {i['parent_asin'] for i in images}!=ids:
        raise ValueError('Catalog identity mismatch')
    for image in images:
        relative=image.get('asset_path')
        if not relative:continue
        candidate=Path(relative)
        if candidate.is_absolute() or '..' in candidate.parts or candidate.parts[:2]!=('images','fixtures'):
            raise ValueError('Unsafe or unauthorized image path')
        data=(root/candidate).read_bytes()
        if hashlib.sha256(data).hexdigest()!=image.get('validation',{}).get('sha256'):
            raise ValueError('Image content differs from reviewed manifest')
        if image.get('rights_status')!='GENERATED_ORIGINAL_FIXTURE':raise ValueError('Image rights status invalid')
    manifest['image_count']=sum(bool(x.get('asset_path')) for x in images)
    manifest['image_rights_status']='GENERATED_FIXTURES_ONLY'
    manifest['authentic_amazon_image_count']=0
    manifest['local_preview_image_count']=0
    manifest['state']='DATA_APPROVED_GENERATED_FIXTURES_PACKAGED_AUTHENTIC_MEDIA_PENDING'
    path.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    (root/'manifests/checksums.sha256').write_text(''.join(f'{files[name]}  {name}\n' for name in sorted(files)),encoding='utf-8')
    return {'file_count':len(files),'image_count':manifest['image_count'],
            'data_approval_status':manifest.get('data_approval_status'),
            'image_rights_status':manifest.get('image_rights_status')}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--acknowledge-reviewed-changes',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(run(args.root,args.acknowledge_reviewed_changes),indent=2))
    except (OSError,ValueError,KeyError) as failure:print(str(failure),file=sys.stderr);sys.exit(2)
