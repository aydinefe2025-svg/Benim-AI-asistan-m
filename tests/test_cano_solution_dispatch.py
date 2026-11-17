import unittest
from core.cano_solution_dispatch import infer_code_goal, actionable_solution

class CanoNaturalCodeDispatchTests(unittest.TestCase):
    def test_direct_software_imperative_requires_no_special_prefix(self):
        self.assertEqual("CANO web sohbetindeki kod hatasını düzelt",
                         infer_code_goal("CANO web sohbetindeki kod hatasını düzelt", []))
    def test_implement_last_solution_without_copy_paste(self):
        previous=[
          {"role":"user","content":"CANO nasıl geliştirilir?"},
          {"role":"assistant","content":"Çözüm: CANO uygulamasında görev kuyruğu bağlantısını düzelt, ardından otomatik test ekle ve Render'da doğrula."},
          {"role":"user","content":"CANO bunu uygula"}
        ]
        result=infer_code_goal("CANO bunu uygula",previous)
        self.assertIn("görev kuyruğu",result)
        self.assertIn("Render",result)
        self.assertLessEqual(len(result),1200)
    def test_research_and_capability_question_not_swallowed(self):
        for q in ("CANO nötron yıldızını araştır", "CANO kendini geliştirebilir misin?", "Bugün hava nasıl?"):
            with self.subTest(q=q):
                self.assertIsNone(infer_code_goal(q,[]))
    def test_no_previous_actionable_solution_returns_none(self):
        self.assertIsNone(infer_code_goal("CANO bunu uygula",[
            {"role":"assistant","content":"Merhaba, size nasıl yardımcı olabilirim?"}
        ]))
    def test_existing_explicit_routing_remains_authoritative(self):
        self.assertIsNone(infer_code_goal("CANO kod: uygulama hatasını düzelt",[]))
        self.assertIsNone(infer_code_goal("CANO görev: araştırma hazırla",[]))
    def test_model_code_request_is_not_accepted_as_user_instruction(self):
        self.assertFalse(actionable_solution("İnternette bilgi buldum ve açıklıyorum."))
        self.assertFalse(actionable_solution("İş kimliği: 1245 · CANO kod işi kalıcı kuyruğa alındı"))
    def test_secret_in_context_never_queues(self):
        messages=[{"role":"assistant","content":"Çözüm: kodu güncelle, test et. sk-"+"X"*40}]
        self.assertIsNone(infer_code_goal("CANO bunu uygula",messages))
