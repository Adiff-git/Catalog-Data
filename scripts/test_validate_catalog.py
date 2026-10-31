import shutil
from pathlib import Path
import tempfile
import unittest
import validate_catalog as module

class PortablePackageTests(unittest.TestCase):
    def test_generated_fixture_package_is_consistent(self):
        report=module.validate(module.ROOT)
        self.assertTrue(report['package_valid'])
        self.assertTrue(report['ready_for_bootstrap'])
        self.assertEqual(report['product_count'],1500)
        self.assertEqual(report['image_count'],1500)

    def test_tampered_package_fails_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'catalog'
            shutil.copytree(module.ROOT,copy)
            with (copy/'data/category_mapping.json').open('a',encoding='utf-8') as output:output.write(' ')
            report=module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertIn('CHECKSUM_MISMATCH:data/category_mapping.json',report['issues'])

    def test_preview_copy_cannot_enter_package(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'catalog'
            shutil.copytree(module.ROOT,copy)
            (copy/'images/B012345678.webp').write_bytes(b'preview-fixture')
            report=module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertIn('UNREFERENCED_IMAGE_ASSET:images/B012345678.webp',report['issues'])

    def test_missing_required_fixture_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'catalog';shutil.copytree(module.ROOT,copy)
            next((copy/'images/fixtures').glob('*.webp')).unlink()
            report=module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertTrue(any(x.startswith('MISSING_OR_UNSAFE_IMAGE_ASSET:') for x in report['issues']))

    def test_corrupt_fixture_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'catalog';shutil.copytree(module.ROOT,copy)
            next((copy/'images/fixtures').glob('*.webp')).write_bytes(b'not-webp')
            report=module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertTrue(any(x.startswith('INVALID_IMAGE:') for x in report['issues']))

    def test_fixture_cannot_claim_licensed_rights(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / 'catalog'
            shutil.copytree(module.ROOT, copy)
            image_manifest = copy / 'manifests/image_manifest.json'
            data = json.loads(image_manifest.read_text(encoding='utf-8'))
            data['images'][0]['rights_status'] = 'LICENSED_FOR_REDISTRIBUTION'
            image_manifest.write_text(json.dumps(data), encoding='utf-8')
            report = module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertTrue(any(code.startswith('INVALID_FIXTURE_AUTHORIZATION:')
                                for code in report['issues']))

    def test_local_product_image_cannot_be_silently_packaged(self):
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / 'catalog'
            shutil.copytree(module.ROOT, copy)
            destination = copy / 'images/products/B012345678.webp'
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(next((copy / 'images/fixtures').glob('*.webp')), destination)
            report = module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertIn('UNREFERENCED_IMAGE_ASSET:images/products/B012345678.webp',
                          report['issues'])

    def test_license_evidence_url_is_not_package_proof(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / 'catalog'
            shutil.copytree(module.ROOT, copy)
            file = copy / 'manifests/image_manifest.json'
            image_manifest = json.loads(file.read_text(encoding='utf-8'))
            row = image_manifest['images'][0]
            asin = row['parent_asin']
            fixture = copy / row['asset_path']
            product_image = copy / f'images/products/{asin}.webp'
            product_image.parent.mkdir(exist_ok=True)
            fixture.rename(product_image)
            row.update(asset_path=f'images/products/{asin}.webp',
                       rights_status='LICENSED_FOR_REDISTRIBUTION',
                       rights_evidence_reference='https://example.com/license',
                       image_status='LICENSED_PRODUCT_IMAGE')
            file.write_text(json.dumps(image_manifest), encoding='utf-8')
            report = module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertIn('IMAGE_RIGHTS_EVIDENCE_PATH_INVALID:images/products/'+asin+'.webp',
                          report['issues'])

    def test_reseal_requires_explicit_acknowledgement(self):
        import reseal_catalog
        with self.assertRaises(ValueError):reseal_catalog.run(module.ROOT)

if __name__=='__main__':unittest.main()
