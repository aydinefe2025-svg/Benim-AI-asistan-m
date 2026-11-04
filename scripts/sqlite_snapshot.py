"""Local-only snapshot/recovery CLI. Destinations must be new directories."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.sqlite_snapshot import snapshot_directory, restore_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    try:
        action = snapshot_directory if args.operation == 'backup' else restore_directory
        print(json.dumps(action(args.source, args.destination), sort_keys=True))
        return 0
    except Exception:
        # Do not expose data, file paths, database contents or connection strings.
        print(json.dumps({'status': 'failed', 'existing_files_overwritten': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
