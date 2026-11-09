import unittest

from core.human_label_progress import (
    decode_human_label_progress, encode_human_label_progress,
)

ALLOWED = {
    "v3": {"a", "b"},
    "v4": {"c"},
}


class HumanLabelProgressTests(unittest.TestCase):
    def test_partial_answers_round_trip_without_other_result_fields(self):
        answers = {"v3": {"a": "supported"}, "v4": {"c": "insufficient"}}
        payload = encode_human_label_progress(answers, ALLOWED)
        decoded = decode_human_label_progress(payload.encode("utf-8"), ALLOWED)
        self.assertEqual(decoded, answers)
        self.assertNotIn("expected", payload)
        self.assertNotIn("predicted", payload)
        self.assertNotIn("answer_key", payload)

    def test_empty_and_incomplete_cohorts_are_valid(self):
        self.assertEqual(
            decode_human_label_progress(
                encode_human_label_progress({}, ALLOWED), ALLOWED),
            {},
        )
        self.assertEqual(
            decode_human_label_progress(
                encode_human_label_progress({"v3": {}}, ALLOWED), ALLOWED),
            {},
        )

    def test_unknown_cohort_or_case_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_human_label_progress({"v7": {"x": "supported"}}, ALLOWED)
        with self.assertRaises(ValueError):
            encode_human_label_progress({"v3": {"not-a-case": "supported"}}, ALLOWED)

    def test_invalid_and_unhashable_labels_are_rejected(self):
        for label in ("— Seçin —", None, [], {"label": "supported"}):
            with self.subTest(label=label), self.assertRaises(ValueError):
                encode_human_label_progress({"v3": {"a": label}}, ALLOWED)

    def test_import_rejects_gold_or_model_fields(self):
        payload = (
            '{"format":"cano-human-label-progress","version":1,'
            '"cohorts":{"v3":{"a":"supported"}},'
            '"expected":{"a":"contradicted"}}'
        )
        with self.assertRaises(ValueError):
            decode_human_label_progress(payload, ALLOWED)

    def test_import_rejects_duplicate_json_fields(self):
        payload = (
            '{"format":"cano-human-label-progress",'
            '"format":"cano-human-label-progress","version":1,"cohorts":{}}'
        )
        with self.assertRaises(ValueError):
            decode_human_label_progress(payload, ALLOWED)

    def test_oversized_backup_is_rejected_before_parsing(self):
        with self.assertRaises(ValueError):
            decode_human_label_progress(b" " * 64_001, ALLOWED)


if __name__ == "__main__":
    unittest.main()
