#!/usr/bin/env python3
"""Create original, illustrative WebP fixtures for the approved catalog identities."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
def generate(root=ROOT):
    root=Path(root)
    products=[json.loads(x) for x in (root/'data/products.jsonl').read_text().splitlines() if x]
    manifest_path=root/'manifests/image_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    entries={x['parent_asin']:x for x in manifest['images']}
    if len(products)!=1500 or len(entries)!=1500:raise ValueError('Expected 1500 catalog identities')
    font=ImageFont.load_default()
    for product in products:
        asin=product['parent_asin'];category=product['product']['category_label']
        entry=entries[asin]
        if entry['product_id_proposal']!=product['product']['id_proposal']:raise ValueError('Identity mismatch')
        color=tuple(60+int(hashlib.sha256(category.encode()).hexdigest()[i:i+2],16)%140 for i in (0,2,4))
        image=Image.new('RGB',(512,512),(245,247,250));draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((48,48,464,464),radius=38,fill=color)
        draw.text((80,170),'ILLUSTRATIVE FIXTURE',font=font,fill='white')
        draw.text((80,210),category[:35],font=font,fill='white')
        draw.text((80,250),asin,font=font,fill='white')
        relative='images/fixtures/'+asin+'.webp';path=root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            from io import BytesIO
            buffer=BytesIO();image.save(buffer,format='WEBP',quality=82,method=4)
            if path.read_bytes()!=buffer.getvalue():raise ValueError('Existing fixture differs: '+asin)
        else:image.save(path,format='WEBP',quality=82,method=4)
        data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
        entry.update(asset_path=relative,status='VALIDATED_AUTHORIZED_ASSET',image_status='GENERATED_FIXTURE',
            rights_status='GENERATED_ORIGINAL_FIXTURE',rights_evidence_reference='scripts/generate_fixture_images.py',
            content_type='image/webp',file_size_bytes=len(data),width=512,height=512,sha256=sha,
            validation={'sha256':sha,'byte_size':len(data),'width':512,'height':512,'content_type':'image/webp'},
            failure_reason=None,local_image_path=None)
    manifest['authorized_image_count']=1500
    manifest['asset_kind']='GENERATED_ILLUSTRATIVE_FIXTURE'
    manifest['authentic_amazon_image_count']=0
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return {'generated_fixture_count':1500}
if __name__=='__main__':print(json.dumps(generate()))
