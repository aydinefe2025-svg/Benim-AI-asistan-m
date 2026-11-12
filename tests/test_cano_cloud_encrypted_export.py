"""Offline-only security and protocol regression checks (no actual DB I/O)."""
import os
import unittest
from unittest.mock import patch
from scripts.cano_cloud_encrypted_export import valid_auth, source_verified, _state

PREFIX='dpg-dbkfp5bm8hqs73bba7u0-a'
DB='research_library_persistent_db'
TOKEN='f'*64
BASE={'CANO_REQUIRED_RENDER_DATABASE': DB, 'CANO_REQUIRED_RENDER_HOST_PREFIX': PREFIX,
      'CANO_RENDER_INTERNAL_URL': f'postgresql://test:password@{PREFIX}.frankfurt-postgres.render.com/{DB}'}

class SecurityTests(unittest.TestCase):
    def test_bearer_rejects_missing_wrong_truncated(self):
        for token in ['', 'x', 'a'*63, TOKEN[:-1]+'e']:
            self.assertFalse(valid_auth('Bearer '+token, TOKEN))
        self.assertFalse(valid_auth(TOKEN,TOKEN))
        self.assertTrue(valid_auth('Bearer '+TOKEN,TOKEN))

    def test_source_pinning_rejects_other_provider(self):
        self.assertFalse(source_verified({**BASE, 'CANO_RENDER_INTERNAL_URL':
            f'postgresql://test:password@other.neon.tech/{DB}'}))
        self.assertFalse(source_verified({**BASE, 'CANO_RENDER_INTERNAL_URL':
            f'postgresql://test:password@{PREFIX}.attacker.test/{DB}'}))

    def test_source_pinning_rejects_wrong_database(self):
        self.assertFalse(source_verified({**BASE, 'CANO_REQUIRED_RENDER_DATABASE': 'wrong'}))

    def test_secure_source_accepted(self):
        self.assertTrue(source_verified(BASE))

    def test_wrong_tls_mode_rejected(self):
        self.assertFalse(source_verified({**BASE, 'CANO_RENDER_INTERNAL_URL':
            BASE['CANO_RENDER_INTERNAL_URL']+'?sslmode=disable'}))

    def test_auth_fail_closed_on_bad_render_configuration(self):
        with patch.dict(os.environ, {'CANO_EXPORT_ACCESS_TOKEN': 'not64chars'}):
            self.assertFalse(valid_auth('Bearer '+TOKEN))

if __name__ == '__main__':
    unittest.main()
