"""Render deployment source pinning: proof-before-mutation unit contracts."""
import unittest

from scripts.cano_render_branch_pin import (
    EXPECTED_LIVE_SHA, REPO, SERVICE_ID, TARGET_BRANCH,
    plan_branch_pin,
)


def service(branch="main", auto="no"):
    return {
        "id": SERVICE_ID, "repo": REPO, "branch": branch,
        "autoDeploy": auto, "autoDeployTrigger": "off",
    }


def live(commit=EXPECTED_LIVE_SHA, status="live"):
    return {"commit": {"id": commit}, "status": status}


class ProductionBranchPinTests(unittest.TestCase):
    def test_verified_live_equals_production_branch_allows_exact_pin(self):
        self.assertEqual(
            (True, "pin_required"),
            plan_branch_pin(service(), live(), EXPECTED_LIVE_SHA),
        )

    def test_already_pinned_is_safe_idempotent_no_write(self):
        self.assertEqual(
            (True, "already_pinned"),
            plan_branch_pin(service(TARGET_BRANCH), live(), EXPECTED_LIVE_SHA),
        )

    def test_live_commit_and_production_branch_disagree_fails_closed(self):
        for change in (
            (service(), live(commit="a" * 40), EXPECTED_LIVE_SHA),
            (service(), live(), "a" * 40),
            (service(), live(commit="a" * 40), "a" * 40),
            (service(), live(status="build_in_progress"), EXPECTED_LIVE_SHA),
        ):
            with self.subTest(change=change):
                allowed, _ = plan_branch_pin(*change)
                self.assertFalse(allowed)

    def test_no_auto_deploy_or_other_service_and_repo_are_ever_allowed(self):
        for item in (
            {**service(), "autoDeploy": "yes"},
            {**service(), "autoDeployTrigger": "commit"},
            {**service(), "id": "srv-other"},
            {**service(), "repo": "https://github.com/attacker/fork"},
            {**service(), "branch": "a-different-branch"},
        ):
            with self.subTest(item=item):
                self.assertFalse(plan_branch_pin(item, live(), EXPECTED_LIVE_SHA)[0])

    def test_missing_or_malformed_proof_does_not_authorize_pinning(self):
        for item in (None, {}, [], "main"):
            with self.subTest(item=item):
                self.assertFalse(plan_branch_pin(item, live(), EXPECTED_LIVE_SHA)[0])
        for item in (None, {}, [], {"status": "live"}, {"status": "live", "commit": {}}):
            with self.subTest(item=item):
                self.assertFalse(plan_branch_pin(service(), item, EXPECTED_LIVE_SHA)[0])
        self.assertFalse(plan_branch_pin(service(), live(), "")[0])


if __name__ == "__main__":
    unittest.main()
