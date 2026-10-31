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
            self.assertTrue(any(x.startswith('MISSING_IMAGE_ASSET:') for x in report['issues']))

    def test_corrupt_fixture_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'catalog';shutil.copytree(module.ROOT,copy)
            next((copy/'images/fixtures').glob('*.webp')).write_bytes(b'not-webp')
            report=module.validate(copy)
            self.assertFalse(report['package_valid'])
            self.assertTrue(any(x.startswith('INVALID_IMAGE:') for x in report['issues']))

    def test_reseal_requires_explicit_acknowledgement(self):
        import reseal_catalog
        with self.assertRaises(ValueError):reseal_catalog.run(module.ROOT)

if __name__=='__main__':unittest.main()
