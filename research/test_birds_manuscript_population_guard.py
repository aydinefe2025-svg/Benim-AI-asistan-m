"""Population alignment claims should fail closed across source date ranges."""
import copy
import unittest
from birds_manuscript_population_guard import audit_population, SOURCES

# SYNTHETIC source profile with counts and sheet labels pinned from original
# observation. True-source CI still must generate the independent JSON receipt.
SHEETS = {
    "UGUISU": [("23 October 2020", 1079,1079), ("13 Feb 2021",1080,1080),
               ("10 April 2021",1111,1101)],
    "RAAVANA": [("13 Feb 2021",1079,1079), ("11 March 2021",1080,1080)],
    "NEPALISAT": [("9 Nov 2020",1080,1080), ("25 Nov 2020",880,880),
                 ("10 April 2021",1080,1080)],
}

class TestPublishedPopulationGuard(unittest.TestCase):
    def source(self):
        sats={}
        for n,(sha,size,raw,complete) in SOURCES.items():
            sats[n]={"git_blob_sha1":sha,"source_size":size,
                     "rows_after_first_total":raw,"numeric_14field_rows":complete,
                     "sheet_count":len(SHEETS[n]),
                     "sheet_details":[{"sheet":nm,"data_rows_after_first":r,
                                       "numeric_14field_rows":c} for nm,r,c in SHEETS[n]]}
        return {"status":"FOUR_SATELLITE_SOURCE_IDENTITIES_AND_OOXML_PROFILE_VERIFIED",
                "satellites":sats}

    def test_original_three_birds_is_different_from_paper_population(self):
        r=audit_population(self.source())
        self.assertEqual(r['publisher_paper']['reported_n'],8439)
        self.assertEqual(r['original_three_birds']['source_rows'],8469)
        self.assertEqual(r['original_three_birds']['complete_14_field_rows'],8459)
        self.assertEqual(r['original_three_birds']['sheets_outside_paper_window'],7)
        self.assertEqual(r['original_three_birds']['source_rows_within_paper_window_by_sheet'],1079)
        self.assertEqual(r['original_three_birds']['source_rows_outside_paper_window_by_sheet'],7390)
        self.assertEqual(r['original_three_birds']['total_sheets'],8)
        self.assertFalse(r['acceptance']['paper_8439_same_population_as_original_workbooks'])
        self.assertFalse(r['acceptance']['published_test_metrics_reproduced'])

    def test_unparseable_sheet_date_fail_closed(self):
        r=self.source()
        r['satellites']['UGUISU']['sheet_details'][0]['sheet']='2020 23 Something Unrecognized'
        with self.assertRaises(ValueError):audit_population(r)

    def test_source_pin_mismatch_fail_closed(self):
        r=self.source()
        r['satellites']['UGUISU']['git_blob_sha1']='0'*40
        with self.assertRaises(ValueError):audit_population(r)

    def test_unverified_source_receipt_fail_closed(self):
        r=self.source()
        r['status']='SYNTHETIC'
        with self.assertRaises(ValueError):audit_population(r)

    def test_sheet_counts_must_reconcile(self):
        r=self.source()
        r['satellites']['RAAVANA']['sheet_details'][0]['data_rows_after_first']+=1
        with self.assertRaises(ValueError):audit_population(r)

if __name__ == '__main__':unittest.main()