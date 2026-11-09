"""Deterministic navigation and fail-closed safety checks: synthetic map only."""
import unittest
from dataclasses import replace
from research.mars_rover_navigation import RoverConfig, SafetyAbort, plan_route, run_demo

TERRAIN = (
    ".............",
    ".sssssssss...",
    ".#######.....",
    "...######....",
    ".............",
)
START = (0, 1)
GOAL = (12, 1)


class MarsRoverNavigationTests(unittest.TestCase):
    def test_hazard_aware_plan_avoids_sand_and_retains_energy_reserve(self):
        result = plan_route(TERRAIN, START, GOAL)
        self.assertEqual(result["path"][0], START)
        self.assertEqual(result["path"][-1], GOAL)
        self.assertEqual(result["sand_cells"], 0)
        self.assertGreaterEqual(result["battery_remaining_wh"], 8.0)
        self.assertEqual(result["autonomous_navigation"], True)

    def test_shortest_route_is_not_necessarily_lowest_risk(self):
        naive = plan_route(TERRAIN, START, GOAL, replace(RoverConfig(), risk_penalty_m=0, available_wh=120))
        aware = plan_route(TERRAIN, START, GOAL)
        self.assertLess(naive["steps"], aware["steps"])
        self.assertGreater(naive["sand_cells"], aware["sand_cells"])
        self.assertGreater(naive["energy_used_wh"], aware["energy_used_wh"])

    def test_rover_never_crosses_blocked_cells_or_teleports(self):
        result = plan_route(TERRAIN, START, GOAL)
        for (x, y), (xx, yy) in zip(result["path"], result["path"][1:]):
            self.assertEqual(abs(x-xx)+abs(y-yy), 1)
            self.assertNotEqual(TERRAIN[yy][xx], "#")

    def test_low_energy_aborts_without_success_claim(self):
        with self.assertRaises(SafetyAbort):
            plan_route(TERRAIN, START, GOAL, replace(RoverConfig(), available_wh=24))

    def test_uncertainty_requires_automatic_relocalization(self):
        ok = plan_route(TERRAIN, START, GOAL)
        self.assertGreater(ok["relocalizations"], 0)
        self.assertLessEqual(ok["max_observed_localization_error_m"], 5.0)
        with self.assertRaises(SafetyAbort):
            plan_route(TERRAIN, START, GOAL, replace(RoverConfig(), allow_relocalization=False))

    def test_unreachable_site_fails_closed(self):
        grid = (".....", ".###.", ".#.#.", ".###.", ".....")
        with self.assertRaises(SafetyAbort):
            plan_route(grid, (0, 0), (2, 2))

    def test_rejects_invalid_grid_symbols_and_blocked_start(self):
        for grid in ((".....", "..."), ("..X", "..."), ("",)):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                plan_route(grid, (0, 0), (1, 0))
        with self.assertRaises(ValueError):
            plan_route(TERRAIN, (1, 2), GOAL)

    def test_invalid_safety_config_rejected(self):
        for config in (replace(RoverConfig(), available_wh=-1),
                       replace(RoverConfig(), cell_m=0),
                       replace(RoverConfig(), battery_reserve_wh=42),
                       replace(RoverConfig(), max_localization_error_m=0)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                plan_route(TERRAIN, START, GOAL, config)

    def test_communication_delay_is_not_per_step_teleoperation(self):
        result = plan_route(TERRAIN, START, GOAL)
        self.assertEqual(result["one_way_latency_s"], 682)
        self.assertFalse(result["remote_teleoperation_per_step"])
        self.assertTrue(result["autonomous_navigation"])

    def test_repeatable_same_inputs_same_route(self):
        self.assertEqual(plan_route(TERRAIN, START, GOAL), plan_route(TERRAIN, START, GOAL))

    def test_demo_distinguishes_synthetic_from_real_mission(self):
        report = run_demo()
        self.assertEqual(report["data_type"], "synthetic_terrain_and_assumptions")
        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["mars_life_detected"])

    def test_goal_equal_start_is_valid_no_energy_use(self):
        result = plan_route(TERRAIN, START, START)
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["energy_used_wh"], 0)


if __name__ == "__main__":
    unittest.main()