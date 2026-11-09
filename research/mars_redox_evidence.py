"""Tiny primary-source numerical audit of published Jezero mineral chemistry.

This analyses only *quoted* illustrative uncertainties from a 2025 Nature
article. No spectra/PDS raw data are accessed, and NO inference of life is made.
Source: https://doi.org/10.1038/s41586-025-09413-0
"""
from __future__ import annotations
from dataclasses import dataclass
import math

SOURCE_DOI = "10.1038/s41586-025-09413-0"


@dataclass(frozen=True)
class QuotedMeasurement:
    element: str
    concentration_ppm: float
    quoted_uncertainty_ppm: float

    @property
    def relative_quoted_uncertainty_pct(self) -> float:
        if (not math.isfinite(self.concentration_ppm)
                or not math.isfinite(self.quoted_uncertainty_ppm)
                or self.concentration_ppm <= 0 or self.quoted_uncertainty_ppm < 0):
            raise ValueError("Invalid quoted concentration/uncertainty")
        return 100 * self.quoted_uncertainty_ppm / self.concentration_ppm


# Nature (2025), text on PIXL observations in high Fe-S region, Apollo Temple.
# These are reported approximate/approaching maxima, NOT a data series.
QUOTED_EXAMPLES = (
    QuotedMeasurement("Zn", 2300, 670),
    QuotedMeasurement("Ni", 2000, 570),
    QuotedMeasurement("Cu", 419, 355),
)


def audit_published_numbers() -> dict:
    return {
        "source_doi": SOURCE_DOI,
        "measurement_context": "Reported near-maximum elemental enrichments in PIXL's high-Fe-S Apollo Temple region; quoted published values only.",
        "elements": [
            {"element": m.element, "concentration_ppm": m.concentration_ppm,
             "quoted_uncertainty_ppm": m.quoted_uncertainty_ppm,
             "relative_quoted_uncertainty_pct": round(m.relative_quoted_uncertainty_pct, 2)}
            for m in QUOTED_EXAMPLES
        ],
        "raw_spectra_reanalysed": False,
        "uncertainty_is_biosignature_probability": False,
        "life_detected": False,
        "caution": "A quoted +/- divided by a quoted concentration does not measure probability of biological origin or independently validate mineral identification.",
    }