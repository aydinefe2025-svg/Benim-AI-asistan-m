"""Select the last verified CANO colony state without resetting history."""
from pathlib import Path

def restore_previous_state(destination: Path, *, run_ids, inspect_artifacts, download):
    """Restore from a verified GitHub artifact; missing history must fail closed."""
    raise NotImplementedError("Restore validation not implemented")
