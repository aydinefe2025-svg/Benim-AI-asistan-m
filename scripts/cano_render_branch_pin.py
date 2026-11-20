"""Fail-closed Render branch pinning for CANO production, no implicit deploy.

This module will only authorize branch switch after matching actual live
commit with the dedicated CANO production branch. It never merges code,
claims Neon tasks or changes auto-deploy settings to an enabled state.
"""
REPO = "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m"
SERVICE_ID = "srv-dbiulm8473hc73amkjtg"
TARGET_BRANCH = "cano-production"
EXPECTED_LIVE_SHA = "db932611dafa599a6c76392abe53e6c4623d4ca1"


def plan_branch_pin(service, latest_deploy, production_sha):
    """Return (allowed, reason) without mutations."""
    return False, "not_implemented"
