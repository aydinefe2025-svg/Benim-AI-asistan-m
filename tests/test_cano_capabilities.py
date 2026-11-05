import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from core.cano_capabilities import capability_reply


class CapabilityTests(unittest.TestCase):
    def test_app_answers_runtime_capabilities_without_any_model_or_network_call(self):
        app = Path(__file__).resolve().parents[1] / 'app.py'
        tree = ast.parse(app.read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'asistani_calistir')
        namespace = {
            '_MEMORY_STORE': object(), '_CANO_OWNER_KEY': 'synthetic-owner',
            'cano_database_url': lambda env: 'synthetic-dsn',
            'os': SimpleNamespace(environ={}),
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(app), 'exec'), namespace)
        # No st, model client or network helper exists in this namespace.
        text = namespace['asistani_calistir']('kendini geliştir cano')
        self.assertIn('giriş hesabına bağlı PostgreSQL', text)

    def test_live_memory_mode_is_reported_without_generic_model_denial(self):
        text = capability_reply('kendini geliştir cano', persistent_memory=True,
                                persistent_colony=True)
        self.assertIn('giriş hesabına bağlı PostgreSQL', text)
        self.assertIn('onayladığın dersler', text)
        self.assertIn('geri yükle', text)
        self.assertNotIn('yeteneğim yok', text)
        self.assertNotIn('tarayıcı deposunu kullanıyor', text)
        self.assertIn('yeniden eğitmez', text)

    def test_browser_only_session_does_not_claim_account_persistence(self):
        text = capability_reply('Hafızan var mı?')
        self.assertIn('tarayıcı deposunu kullanıyor', text)
        self.assertIn('kalıcı hesap yedeği bağlı değil', text)

    def test_natural_self_learning_phrases_get_capability_answer(self):
        for query in (
            'Bilgi toplayarak kendini geliştir',
            'Bilgi toplayarak kendini geliştirebilir misin?',
            'Fiziksel laboratuvar olmadan kendini geliştirebilir miyiz?',
        ):
            with self.subTest(query=query):
                text = capability_reply(query, persistent_memory=True,
                                        persistent_colony=True)
                self.assertIn('onayladığın dersler', text)
                self.assertIn('model ağırlıklarını yeniden eğitmez', text)

    def test_domain_tasks_are_not_replaced_with_a_capability_answer(self):
        for task in ('Kendini geliştiren robot tasarla', 'CANO için kalıcı hafıza geliştir',
                     '2+2 kaç?', 'kendini geliştir ve güneş enerjisini araştır'):
            self.assertIsNone(capability_reply(task))
