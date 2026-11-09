"""Audit only publicly quoted Jezero chemistry measurements; no raw spectra."""
import json
from research.mars_redox_evidence import audit_published_numbers

if __name__ == "__main__":
    print(json.dumps(audit_published_numbers(), indent=2))
