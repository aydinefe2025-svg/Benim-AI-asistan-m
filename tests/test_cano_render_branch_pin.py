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


    def test_pinning_calls_only_one_branch_patch_after_proof(self):
        from unittest.mock import patch
        from scripts.cano_render_branch_pin import pin_service_branch
        name = "scripts.cano_render_branch_pin."
        with (patch(name + "_production_sha",
                    side_effect=[EXPECTED_LIVE_SHA] * 3),
              patch(name + "_service",
                    side_effect=[service(), service(TARGET_BRANCH)]),
              patch(name + "_latest_deploy",
                    side_effect=[live(), live()]),
              patch(name + "_read_json") as request):
            self.assertEqual(
                "pinned_and_verified", pin_service_branch("test-key")
            )
            request.assert_called_once_with(
                "https://api.render.com/v1/services/" + SERVICE_ID,
                token="test-key", method="PATCH",
                body={"branch": TARGET_BRANCH},
            )

    def test_missing_api_key_makes_no_external_calls(self):
        from unittest.mock import patch
        from scripts.cano_render_branch_pin import (
            VerificationBlocked, pin_service_branch,
        )
        with patch("scripts.cano_render_branch_pin._production_sha") as sha:
            with self.assertRaises(VerificationBlocked):
                pin_service_branch("")
            sha.assert_not_called()

    def test_production_branch_moving_aborts_before_patch(self):
        from unittest.mock import patch
        from scripts.cano_render_branch_pin import (
            VerificationBlocked, pin_service_branch,
        )
        name = "scripts.cano_render_branch_pin."
        with (patch(name + "_production_sha",
                    side_effect=[EXPECTED_LIVE_SHA, "a" * 40]),
              patch(name + "_service", return_value=service()),
              patch(name + "_latest_deploy", return_value=live()),
              patch(name + "_read_json") as request):
            with self.assertRaises(VerificationBlocked):
                pin_service_branch("test-key")
            request.assert_not_called()



if __name__ == "__main__":
    unittest.main()
