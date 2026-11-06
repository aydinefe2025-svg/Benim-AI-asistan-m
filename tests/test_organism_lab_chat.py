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
            "simülasyon sonucu ne oldu", load_records=lambda: [])
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


if __name__ == "__main__":
    unittest.main()
