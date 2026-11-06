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
        text = namespace['asistani_calistir']('kendini geliştir cano')
        self.assertIn('hesap sahibine bağlı PostgreSQL', text)

    def test_growth_is_explained_as_a_repeatable_workflow(self):
        text = capability_reply('kendini geliştir cano', persistent_memory=True,
                                persistent_colony=True)
        for phrase in ('hedefimiz CANO’nun bilgisini', 'uzman ekibini',
                       'planlama, araştırma, eleştiri ve sonuç',
                       'sonraki uygun görevlerde bağlam',
                       'hesap sahibine bağlı PostgreSQL',
                       'Ekibi çalıştır — 4 aşama',
                       'modelin kendi ağırlıklarını otomatik eğitmesi anlamına gelmez'):
            self.assertIn(phrase, text)

    def test_browser_only_session_does_not_claim_account_persistence(self):
        text = capability_reply('Hafızan var mı?')
        self.assertIn('tarayıcı deposunu kullanıyor', text)
        self.assertIn('kalıcı büyüme için hesap bağlantılı depolama gerekir', text)

    def test_natural_self_learning_phrases_get_growth_answer(self):
        for query in (
            'Bilgi toplayarak kendini geliştir',
            'Bilgi toplayarak kendini geliştirebilir misin?',
            'Fiziksel laboratuvar olmadan kendini geliştirebilir miyiz?',
        ):
            with self.subTest(query=query):
                text = capability_reply(query, persistent_memory=True,
                                        persistent_colony=True)
                self.assertIn('hedefimiz CANO’nun bilgisini', text)
                self.assertIn('onayladığın dersleri', text)
                self.assertIn('dijital simülasyon', text)

    def test_general_capability_questions_receive_growth_first_answer(self):
        for query in (
            'Ne işler yapabilirsin?', 'Neler yapabilirsin CANO?',
            'Hangi işleri yapabilirsin?', 'Yeteneklerin neler?',
        ):
            with self.subTest(query=query):
                text = capability_reply(query, persistent_memory=True,
                                        persistent_colony=True)
                self.assertIn('bilgisini, uzman ekibini ve araştırma kapasitesini', text)
                self.assertIn('Ekibi çalıştır — 4 aşama', text)
                self.assertNotIn('takvim veya hatırlatıcı oluşturamam', text)

    def test_domain_tasks_are_not_replaced_with_a_capability_answer(self):
        for task in ('Kendini geliştiren robot tasarla', 'CANO için kalıcı hafıza geliştir',
                     '2+2 kaç?', 'kendini geliştir ve güneş enerjisini araştır',
                     'CANO için araştırma görevi oluştur'):
            self.assertIsNone(capability_reply(task))
