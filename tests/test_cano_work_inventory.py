import unittest
from unittest.mock import Mock
from core.cano_work_inventory import work_inventory_reply

class WorkInventory(unittest.TestCase):
    def test_exact_mobile_question_reads_owner_sources_not_model(self):
        memory=Mock(return_value=[{"text":"not a title","id":"a"}])
        research=Mock(return_value=[{"title":"EOS calibration","status":"planned"}])
        queue=Mock(return_value=[{"goal":"Ayrı görev","state":"review_pending"}])
        code=Mock(return_value=[{"goal":"CANO düzeltmesi","status":"deployed"}])
        response=work_inventory_reply("Hafızandaki çalışmalarımız nelerdir?",authenticated=True,
            memory_loader=memory,research_loader=research,queue_loader=queue,code_loader=code)
        self.assertIn("EOS calibration",response)
        self.assertIn("CANO düzeltmesi",response)
        self.assertIn("Ayrı görev",response)
        self.assertIn("Hafıza notları: 1",response)
        self.assertNotIn("not a title",response)
        for loader in (memory,research,queue,code):loader.assert_called_once_with()

    def test_unauthenticated_never_loads_any_source(self):
        load=Mock(side_effect=AssertionError("must not read"))
        response=work_inventory_reply("Hafızandaki çalışmalarımız nelerdir?",authenticated=False,
            memory_loader=load,research_loader=load,queue_loader=load,code_loader=load)
        self.assertIn("giriş",response)
        load.assert_not_called()

    def test_missing_and_unavailable_not_empty(self):
        response=work_inventory_reply("Hafızandaki çalışmalarımız nelerdir?",authenticated=True,
            memory_loader=Mock(side_effect=RuntimeError("secret-error")),research_loader=lambda:[],
            queue_loader=None,code_loader=lambda:[])
        self.assertIn("Hafıza notları: okunamadı",response)
        self.assertIn("Araştırma görevleri: 0",response)
        self.assertIn("Onaylı kuyruk: yapılandırılmamış",response)
        self.assertNotIn("secret-error",response)

    def test_non_inventory_requests_pass_through(self):
        load=Mock()
        for prompt in ("Hafızandaki çalışmaları sil", "CANO kod: hafızadaki çalışmaları getir",
                       "EOS araştırmasını ayrıntılı açıkla", "Hafızana kaydet"):
            self.assertIsNone(work_inventory_reply(prompt,authenticated=True,memory_loader=load,
                research_loader=load,queue_loader=load,code_loader=load))
        load.assert_not_called()
