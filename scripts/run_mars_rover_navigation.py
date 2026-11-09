"""Reproduce a synthetic rover route-safety comparison (no network)."""
import json
from research.mars_rover_navigation import run_demo

if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, ensure_ascii=False))
