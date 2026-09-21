import unittest
from publish_release import verify_assets
from release_bundle import sha256


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.files = {'package.zip': b'package'}
        self.asset = {'name': 'package.zip', 'state': 'uploaded', 'size': 7, 'digest': 'sha256:' + sha256(b'package')}

    def test_uploaded_digest_and_size_must_match(self):
        verify_assets({'assets': [self.asset]}, self.files)
        for change in ({'digest': 'sha256:' + '0' * 64}, {'size': 1}, {'state': 'new'}, {'digest': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_assets({'assets': [{**self.asset, **change}]}, self.files)

    def test_missing_and_unexpected_assets_block_publication(self):
        with self.assertRaises(ValueError):
            verify_assets({'assets': []}, self.files)
        with self.assertRaises(ValueError):
            verify_assets({'assets': [{**self.asset, 'name': 'private.log'}]}, self.files)
        verify_assets({'assets': []}, self.files, require_all=False)


if __name__ == '__main__':
    unittest.main()
