"""Offline-only security and protocol regression checks (no actual DB I/O)."""
import os
import unittest
from unittest.mock import patch
from scripts.cano_cloud_encrypted_export import valid_auth, source_verified, _state, _auto_upload_worker, _worker

PREFIX='dpg-dbkfp5bm8hqs73bba7u0-a'
DB='research_library_persistent_db'
TOKEN='f'*64
BASE={'CANO_REQUIRED_RENDER_DATABASE': DB, 'CANO_REQUIRED_RENDER_HOST_PREFIX': PREFIX,
      'CANO_RENDER_INTERNAL_URL': f'postgresql://test:password@{PREFIX}.frankfurt-postgres.render.com/{DB}'}

class SecurityTests(unittest.TestCase):
    def test_exporter_docker_image_contains_direct_script_imports(self):
        """All exporter imports must be included in its isolated Docker image."""
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse(
            (root / 'scripts' / 'cano_cloud_encrypted_export.py').read_text('utf-8')
        )
        required = sorted({
            node.module.split('.')[1]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module and node.module.startswith('scripts.')
        })
        dockerfile = (root / 'Dockerfile.cano-pg18-export').read_text('utf-8')
        self.assertTrue(required)
        for module in required:
            self.assertIn(
                f'COPY scripts/{module}.py /app/scripts/{module}.py',
                dockerfile,
                f'Exporter container omits directly imported scripts.{module}',
            )

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

    def test_auto_upload_rejects_invalid_destination_without_dump(self):
        with patch.dict(os.environ, {'CANO_NOTION_UPLOAD_URL': 'https://example.com/v1/file_uploads/id/send', 'CANO_NOTION_UPLOAD_AUTH': 'Bearer placeholder-placeholder'}, clear=True):
            with patch('scripts.cano_cloud_encrypted_export._worker', side_effect=AssertionError('dump should not run')):
                _auto_upload_worker()
                self.assertEqual('failed', _state['offsite_phase'])
                _state['offsite_phase'] = 'not_started'

    def test_auth_fail_closed_on_bad_render_configuration(self):
        with patch.dict(os.environ, {'CANO_EXPORT_ACCESS_TOKEN': 'not64chars'}):
            self.assertFalse(valid_auth('Bearer '+TOKEN))

    def test_worker_reports_safe_failure_stage_without_exception_text(self):
        _state.update(phase='idle', error='')
        with patch('scripts.cano_cloud_encrypted_export.configured', return_value=True), \
             patch('scripts.cano_cloud_encrypted_export._source_table_count',
                   side_effect=RuntimeError('postgres://secret-password')):
            _worker()
        self.assertEqual('failed', _state['phase'])
        self.assertEqual('source_inventory', _state['error'])
        self.assertNotIn('secret-password', _state['error'])

if __name__ == '__main__':
    unittest.main()
