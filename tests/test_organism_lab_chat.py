import unittest

from core.organism_lab_chat import organism_lab_chat_reply


class OrganismLabChatTests(unittest.TestCase):
    def test_campaign_answer_uses_archived_metrics_and_never_invents_genome_similarity(self):
        report = {
            "design": {"seeds": [0, 1], "steps": 8, "resource_levels_per_tick": [2]},
            "observations": [{}, {}],
            "results": [{
                "resource_per_tick": 2,
                "paired_seeds": 2,
                "paired_population_difference": {
                    "mean": 3.5, "ci95_low": 2.0, "ci95_high": 5.0,
                },
            }],
        }
        reply = organism_lab_chat_reply(
            "Az önceki genom karşılaştırmasının sonucunu açıkla",
            load_records=lambda: [{"kind": "campaign", "document": report}],
        )
        self.assertIn("3.50 organizmaydı", reply)
        self.assertIn("gerçek hücre, doğa veya robot davranışını kanıtlamaz", reply)
        self.assertNotIn("%85", reply)
        self.assertNotIn("genetik uzaklık", reply)

    def test_archive_failure_says_result_was_not_verified(self):
        def fail():
            raise OSError("private connection detail")

        reply = organism_lab_chat_reply("laboratuvar sonucu nedir", load_records=fail)
        self.assertIn("doğrulayamadım", reply)
        self.assertNotIn("private connection detail", reply)

    def test_empty_archive_does_not_guess(self):
        reply = organism_lab_chat_reply(
            "Organizmalar Laboratuvarı simülasyon sonucu ne oldu", load_records=lambda: [])
        self.assertIn("sonuç uydurmayacağım", reply)
        self.assertNotIn("%85", reply)

    def test_world_answer_uses_only_saved_counts_and_caveat(self):
        reply = organism_lab_chat_reply(
            "Dijital dünya simülasyonunun sonucu ne?",
            load_records=lambda: [{
                "kind": "world",
                "document": {"robots": 1, "organisms": 4, "successful_routes": 2},
            }],
        )
        self.assertIn("Sanal organizma: 4", reply)
        self.assertIn("gerçek robot veya canlı ölçümü değildir", reply)

    def test_unrelated_chat_is_left_to_normal_assistant(self):
        self.assertIsNone(organism_lab_chat_reply("Merhaba, nasılsın?"))

    def test_general_genome_question_is_left_to_normal_assistant(self):
        self.assertIsNone(organism_lab_chat_reply("Genom nedir?"))


    def test_explicit_run_command_executes_and_reports_persisted_only_after_callback(self):
        from core.organism_lab_chat import execute_organism_lab_request

        calls = []
        result = {"report": {
            "design": {"seeds": [0, 1], "steps": 4, "resource_levels_per_tick": [1]},
            "observations": [{}, {}],
            "results": [{"resource_per_tick": 1, "paired_seeds": 2,
                         "paired_population_difference": {
                             "mean": 1.25, "ci95_low": 0.5, "ci95_high": 2.0}}],
        }, "json": b"campaign-json"}
        reply, returned = execute_organism_lab_request(
            "Organizmalar laboratuvarında genom karşılaştırmasını çalıştır",
            run_campaign=lambda: calls.append("run") or result,
            save_campaign=lambda data: calls.append(("save", data)),
        )
        self.assertEqual(calls, ["run", ("save", b"campaign-json")])
        self.assertIs(returned, result)
        self.assertIn("kalıcı arşive yazıldı ve geri okunarak doğrulandı", reply)
        self.assertIn("1.25 organizmaydı", reply)

    def test_explicit_run_without_archive_never_claims_persistence(self):
        from core.organism_lab_chat import execute_organism_lab_request

        result = {"report": {
            "design": {"seeds": [0, 1], "steps": 4, "resource_levels_per_tick": [1]},
            "observations": [{}, {}],
            "results": [{"resource_per_tick": 1, "paired_seeds": 2,
                         "paired_population_difference": {
                             "mean": 1.25, "ci95_low": 0.5, "ci95_high": 2.0}}],
        }, "json": b"campaign-json"}
        reply, _ = execute_organism_lab_request(
            "Genom karşılaştırmasını başlat",
            run_campaign=lambda: result,
        )
        self.assertIn("yalnızca mevcut oturumda", reply)
        self.assertNotIn("kalıcı arşive yazıldı", reply)

    def test_save_failure_never_claims_saved(self):
        from core.organism_lab_chat import execute_organism_lab_request

        result = {"report": {
            "design": {"seeds": [0, 1], "steps": 4, "resource_levels_per_tick": [1]},
            "observations": [{}, {}],
            "results": [{"resource_per_tick": 1, "paired_seeds": 2,
                         "paired_population_difference": {
                             "mean": 1.25, "ci95_low": 0.5, "ci95_high": 2.0}}],
        }, "json": b"campaign-json"}
        def fail(_data):
            raise OSError("database detail")
        reply, _ = execute_organism_lab_request(
            "Laboratuvarda dijital deneyi çalıştır",
            run_campaign=lambda: result, save_campaign=fail,
        )
        self.assertIn("kalıcı kayıt/geri okuma doğrulanamadı", reply)
        self.assertNotIn("database detail", reply)

    def test_question_or_general_chat_never_runs_simulation(self):
        from core.organism_lab_chat import execute_organism_lab_request

        for message in (
            "Laboratuvar nasıl çalışıyor?",
            "Genom karşılaştırmasının sonucu ne?",
            "Merhaba, nasılsın?",
        ):
            with self.subTest(message=message):
                self.assertIsNone(execute_organism_lab_request(
                    message, run_campaign=lambda: self.fail("must not run")))


if __name__ == "__main__":
    unittest.main()
