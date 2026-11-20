"""CANO bounded release eligibility: reject malicious or incomplete PR evidence."""
import unittest

from scripts.cano_release_eligibility import assess, REPO, SOURCE

PR = {
    "state": "open",
    "number": 711,
    "head": {
        "sha": "a" * 40,
        "ref": "cano/owner-job-689de029-progress-iterator",
        "repo": {"full_name": REPO},
    },
    "base": {"ref": "main", "repo": {"full_name": REPO}},
    "changed_files": 2,
}
FILES = [
    {
        "filename": SOURCE,
        "status": "modified",
        "additions": 3,
        "deletions": 0,
        "patch": "@@ -67,2 +67,5 @@\n+    # Materialize only once\n+    jobs = list(jobs)\n+    stats = summarize_recent_code_jobs(jobs)\n",
    },
    {
        "filename": "tests/test_cano_owner_code_progress.py",
        "status": "modified",
        "additions": 12,
        "deletions": 0,
        "patch": "@@ -40,1 +40,13 @@\n+    def test_one_pass(self):\n+        assert True\n",
    },
]


def copy_pr():
    return {
        **PR,
        "head": {**PR["head"], "repo": dict(PR["head"]["repo"])},
        "base": {**PR["base"], "repo": dict(PR["base"]["repo"])},
    }


def copy_files():
    return [dict(f) for f in FILES]


class ReleaseEligibilityTests(unittest.TestCase):
    def test_legitimate_narrow_owner_progress_fix_is_preapproved(self):
        self.assertEqual((True, "bounded_diff_eligible"), assess(copy_pr(), copy_files()))

    def test_wrong_repo_branch_base_head_sha_or_closed_pr_are_not_preapproved(self):
        changes = [
            ("head", {"repo": {"full_name": "other/attacker"}}),
            ("head", {"ref": "cano-autodev-other"}),
            ("head", {"sha": "not-sha"}),
            ("base", {"ref": "feature"}),
            ("base", {"repo": {"full_name": "other/attacker"}}),
            ("state", "closed"),
            ("number", True),
        ]
        for attr, value in changes:
            with self.subTest(attr=attr, change=value):
                pr = copy_pr()
                if attr in {"head", "base"}:
                    pr[attr].update(value)
                else:
                    pr[attr] = value
                self.assertFalse(assess(pr, copy_files())[0])

    def test_no_unreviewed_auth_database_workflows_or_other_scope(self):
        for outside in (
            "core/authentication.py",
            "core/cano_code_jobs.py",
            "scripts/cano_autodev_worker.py",
            ".github/workflows/test.yml",
            "requirements.txt",
            "app.py",
        ):
            with self.subTest(path=outside):
                files = copy_files()
                files[0]["filename"] = outside
                self.assertEqual("outside_bounded_scope" if SOURCE in {f["filename"] for f in files} else "missing_source_or_regression",
                                 assess(copy_pr(), files)[1])

    def test_missing_regression_or_duplicate_path_is_rejected(self):
        files = copy_files()
        files[1]["filename"] = "core/cano_development_status.py"
        self.assertFalse(assess(copy_pr(), files)[0])
        files = copy_files()
        files[1]["filename"] = "core/authentication.py"
        self.assertFalse(assess(copy_pr(), files)[0])

    def test_missing_patch_or_binary_or_rename_is_rejected(self):
        for key, val in (("patch", None), ("status", "renamed"),
                         ("additions", None), ("deletions", -1)):
            with self.subTest(key=key):
                files = copy_files()
                files[0][key] = val
                self.assertFalse(assess(copy_pr(), files)[0])

    def test_unverified_number_of_changed_files_fails_closed(self):
        pr = copy_pr()
        pr["changed_files"] = 3
        self.assertEqual((False, "incomplete_diff"), assess(pr, copy_files()))

    def test_dangerous_additions_are_rejected_even_with_passing_ci(self):
        snippets = (
            "+    import os\n",
            "+    open('/tmp/leak', 'w')\n",
            "+    eval('1 + 1')\n",
            "+    st.secrets.get('key')\n",
            "+    st.session_state['account']\n",
            "+    __import__('subprocess')\n",
            "+    requests.get('https://example.com')\n",
            "+    data = globals()\n",
            "+    token = 'hidden'\n",
        )
        for line in snippets:
            with self.subTest(line=line):
                files = copy_files()
                files[0]["patch"] = "@@ -1 +1 @@\n" + line
                self.assertEqual((False, "unsafe_source_addition"),
                                 assess(copy_pr(), files))

    def test_private_owner_data_must_not_flow_to_new_ui_calls(self):
        # A patch can pass syntax and normal CI while disclosing owner-only
        # goal text. Static low-risk auto-release must reject such additions.
        snippets = (
            "+    st.info(jobs)\n",
            "+    st.write(row.get('goal'))\n",
            "+    st.caption(row['owner_key'])\n",
            "+    st.json(records)\n",
            "+    st.link_button('Owner', str(row.get('goal')))\n",
            "+    print(jobs)\n",
        )
        for line in snippets:
            with self.subTest(line=line):
                files = copy_files()
                files[0]["patch"] = "@@ -1 +1 @@\n" + line
                self.assertFalse(assess(copy_pr(), files)[0])

    def test_removing_existing_source_guards_cannot_be_auto_released(self):
        # A PR could remove a receipt-validation guard and still add only a
        # harmless source line. The previous policy only screened additions.
        files = copy_files()
        files[0]["deletions"] = 1
        files[0]["additions"] = 1
        files[0]["patch"] = (
            "@@ -1,2 +1,2 @@\n"
            "-    if not _CANONICAL_CI.fullmatch(ci):\n"
            "+    # No extra imports or suspicious calls added\n"
        )
        self.assertEqual(
            (False, "source_deletion_requires_review"),
            assess(copy_pr(), files),
        )

    def test_redefining_receipt_validator_cannot_be_auto_released(self):
        # A duplicate definition can shadow the existing private-receipt
        # validator without any forbidden import or API call.
        files = copy_files()
        files[0]["additions"] = 2
        files[0]["patch"] = (
            "@@ -1,0 +1,2 @@\n"
            "+def _safe_deployed_receipts(rows):\n"
            "+    return iter(())\n"
        )
        self.assertEqual(
            (False, "unsafe_source_addition"),
            assess(copy_pr(), files),
        )

    def test_too_large_source_or_test_change_requires_review(self):
        for index, key, count in ((0, "additions", 41),
                                  (0, "deletions", 41),
                                  (1, "additions", 251)):
            with self.subTest(index=index, key=key):
                files = copy_files()
                files[index][key] = count
                self.assertFalse(assess(copy_pr(), files)[0])

    def test_text_only_comment_is_not_equivalent_to_safety_receipt(self):
        pr = copy_pr()
        pr["changed_files"] = "2"
        self.assertFalse(assess(pr, copy_files())[0])

    def test_malformed_input_is_rejected_without_exception(self):
        self.assertEqual((False, "malformed_input"), assess(None, []))
        self.assertFalse(assess({}, [{}])[0])


if __name__ == "__main__":
    unittest.main()
