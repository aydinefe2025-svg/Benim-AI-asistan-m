import unittest

from birds_published_panel_rules import panel_flags, PANEL_COLUMNS

def datum(index, seconds, v=1800.0, i=80.0, panel="PY"):
    vals={}
    for pp,(vc,ic) in PANEL_COLUMNS.items():
        vals[vc]=float(v if pp==panel else 4000)
        vals[ic]=float(i if pp==panel else 100)
    return {"row":index,"t":seconds,"vals":vals}

class TestPublisherPanelRules(unittest.TestCase):
    def test_type1_below_1200_only_and_exact_boundary(self):
        seq=[datum(2,0,1199.9),datum(3,10,1200),datum(4,20,1800)]
        flags,panel=panel_flags(seq,max_gap_seconds=100)
        self.assertEqual(flags["type1"],{2})
        self.assertEqual(panel["PY"]["type1"],1)
        self.assertEqual(panel["PX"]["type1"],0)

    def test_type2_requires_three_consecutive_voltage_rows(self):
        seq=[datum(2,0,2500,20),datum(3,90,2300,49.9),datum(4,180,2700,20)]
        f,p=panel_flags(seq,max_gap_seconds=100)
        self.assertEqual(f["type2"],{3})
        self.assertEqual(p["PY"]["type2"],1)

    def test_breaks_on_missing_source_row(self):
        seq=[datum(2,0,2500,20),datum(4,90,2500,20),datum(5,180,2500,20)]
        self.assertEqual(panel_flags(seq)[0]["type2"],set())

    def test_three_window_rejected_by_large_clock_gaps(self):
        seq=[datum(2,0,2500,20),datum(3,500,2500,20),datum(4,1000,2500,20)]
        self.assertEqual(panel_flags(seq)[0]["type2"],{3})
        self.assertEqual(panel_flags(seq,max_gap_seconds=100)[0]["type2"],set())

    def test_current_bound_exclusive(self):
        seq=[datum(2,0,2500,20),datum(3,10,2500,50),datum(4,20,2500,20)]
        self.assertEqual(panel_flags(seq)[0]["type2"],set())

    def test_strict_timestamp_order(self):
        seq=[datum(2,0,2500,20),datum(3,0,2500,20),datum(4,90,2500,20)]
        self.assertEqual(panel_flags(seq)[0]["type2"],set())

    def test_voltage_window_inclusive(self):
        seq=[datum(2,0,2000,20),datum(3,10,3000,20),datum(4,20,2000,20)]
        self.assertEqual(panel_flags(seq)[0]["type2"],{3})

    def test_three_window_does_not_mix_panels(self):
        a,b,c=datum(2,0,2500,20),datum(3,10,2500,20,panel="PX"),datum(4,20,2500,20)
        self.assertEqual(panel_flags([a,b,c])[0]["type2"],set())

    def test_two_sample_window_cannot_trigger(self):
        self.assertEqual(panel_flags([datum(2,0,2500,20),datum(3,10,2500,20)])[0]["type2"],set())

if __name__=="__main__":
    unittest.main()
