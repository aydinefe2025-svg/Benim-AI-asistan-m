"""Tests for original-source native BaSyTec TXT and independent I dt integration."""
import hashlib
import io
import unittest
from unittest.mock import patch
import zipfile
from research.battery_curve_audit import bayreuth_two_cell_independent_integral as m


def synth_zip(cell="F0001", discharge_ah=-0.1, charge_ah=0.11, discharge_line="17", charge_line="15"):
    hdr = "~Time[h],DataSet,t-Step[h],t-Set[h],Line,Command,U[V],I[A],Ah[Ah],Ah-Step,Wh[Wh],Cyc-Count,State\n"
    rows=["0,1,0,0,17,Discharge,3.6,-0.1,0,0,0,1,1",
          f"0.5,2,0.5,0.5,17,Discharge,3.4,-0.1,0,{discharge_ah/2},0,1,1",
          f"1,3,1,1,17,Discharge,3,-0.1,0,{discharge_ah},0,1,1",
          "1.1,4,0,0,15,Charge,3.0,0.11,0,0,0,1,1",
          f"1.6,5,0.5,0.5,15,Charge,3.6,0.11,0,{charge_ah/2},0,1,1",
          f"2.1,6,1,1,15,Charge,4.2,0.11,0,{charge_ah},0,1,1"]
    rows=[r.replace(",17,Discharge,", f",{discharge_line},Discharge,").replace(",15,Charge,", f",{charge_line},Charge,") for r in rows]
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ("M0001_checkup.txt","M0003_checkup.txt"):
            z.writestr(f"{cell}/{name}",hdr+"\n".join(rows)+"\n")
    return buf.getvalue()


class TestGenuineSourceCoulometry(unittest.TestCase):
    def test_known_constant_current_exact_independent_integral(self):
        data=synth_zip()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            q=m.scan_checkup(z,"F0001/M0001_checkup.txt")
        self.assertEqual(q["rows_parsed"],6)
        a=q["selected_step_profiles"]["discharge"]
        self.assertAlmostEqual(a["integral_trapezoid_Ah"],0.1,11)
        self.assertAlmostEqual(a["integral_right_Ah"],0.1,11)
        self.assertAlmostEqual(a["source_increment_Ah"],0.1,11)
        self.assertEqual(a["plan_line"],"17")
        b=q["selected_step_profiles"]["charge"]
        self.assertAlmostEqual(b["integral_trapezoid_Ah"],0.11,11)

    def test_mismatch_of_device_capacity_is_detected(self):
        data=synth_zip(discharge_ah=-0.2)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            q=m.scan_checkup(z,"F0001/M0001_checkup.txt")
        a=q["selected_step_profiles"]["discharge"]
        self.assertAlmostEqual(a["integral_trapezoid_minus_source_increment_mAh"],-100,8)

    def test_reject_wrong_md5(self):
        payload=synth_zip()
        with patch.dict(m.SOURCE_FILES,{"F0001":{"md5":"0"*32,"size":len(payload)}}):
            with self.assertRaisesRegex(ValueError,"MD5 mismatch"):
                m.validate_zip(payload,"F0001")

    def test_fail_closed_wrong_zip_size(self):
        payload=synth_zip()
        with patch.dict(m.SOURCE_FILES,{"F0001":{"md5":hashlib.md5(payload).hexdigest(),"size":len(payload)+5}}):
            with self.assertRaisesRegex(ValueError,"byte-count"):
                m.validate_zip(payload,"F0001")

    def test_traversal_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr("../M0001_checkup.txt","hello")
            z.writestr("F0001/M0003_checkup.txt","hi")
        data=b.getvalue()
        with patch.dict(m.SOURCE_FILES,{"F0001":{"md5":hashlib.md5(data).hexdigest(),"size":len(data)}}):
            with self.assertRaisesRegex(ValueError,"path traversal"):
                m.validate_zip(data,"F0001")

    def test_two_original_cells_and_delta_no_causal_claims(self):
        a=synth_zip("F0001");b=synth_zip("F0002",discharge_ah=-0.09,discharge_line="27",charge_line="25")
        with patch.dict(m.SOURCE_FILES,{"F0001":{"md5":hashlib.md5(a).hexdigest(),"size":len(a)},"F0002":{"md5":hashlib.md5(b).hexdigest(),"size":len(b)}}):
            with patch.object(m, 'infer_stage_line_offset', return_value={'offset_inferred': True, 'beginning_minus_ending_plan_line_offset':0}):
                x=m.analyze({"F0001":a,"F0002":b})
        self.assertEqual(x["distinct_original_source_cells"],2)
        self.assertTrue(x["not_an_instrument_calibration"])
        self.assertTrue(x["not_48_cells_processed"])
        self.assertAlmostEqual(x["comparison"]["F0002"]["paired_measurement"]["discharge"]["source_step_delta_mAh"],0)
        self.assertEqual(x["comparison"]["F0002"]["paired_measurement"]["discharge"]["beginning_plan_line"],"27")
        self.assertEqual(x["comparison"]["F0002"]["paired_measurement"]["charge"]["beginning_plan_line"],"25")

    def test_actual_source_line_offsets_require_multiple_physical_step_controls(self):
        def p(line,ah,start,end,hrs):
            return {"plan_line":str(line),"source_peak_Ah_Step_abs_Ah":ah,
                    "row_count":3000,"start_measured_voltage_V":start,
                    "last_measured_voltage_V":end,"time_h_span":hrs}
        begin={"candidate_summary_by_command":{
            "charge":[p(21,.1175,3.12,4.2,2.37),p(33,.1171,3.03,4.20,18.9)],
            "discharge":[p(23,.11755,4.19,3.0,2.18),p(35,.1170,4.19,3.0,18.87)]}}
        end={"candidate_summary_by_command":{
            "charge":[p(15,.1145,3.03,4.2,2.32),p(27,.1127,3.03,4.20,18.17)],
            "discharge":[p(17,.1131,4.195,3.0,2.11),p(29,.1128,4.19,3.0,18.2)]}}
        d=m.infer_stage_line_offset(begin,end)
        self.assertTrue(d["offset_inferred"])
        self.assertEqual(d["beginning_minus_ending_plan_line_offset"],6)
        self.assertEqual(d["matched_discharge_line_pairs"],2)
        self.assertEqual(d["matched_charge_line_pairs"],2)
        a,b=m.select_matched_source_step(begin,end,'discharge',6)
        self.assertEqual((a['plan_line'],b['plan_line']),('23','17'))

    def test_reject_single_matching_step_as_proven_program(self):
        p={"plan_line":"23","source_peak_Ah_Step_abs_Ah":.12,"row_count":100,
           "start_measured_voltage_V":4.19,"last_measured_voltage_V":3.0,"time_h_span":2.2}
        q={"plan_line":"17","source_peak_Ah_Step_abs_Ah":.11,"row_count":90,
           "start_measured_voltage_V":4.2,"last_measured_voltage_V":3.0,"time_h_span":2.1}
        x=m.infer_stage_line_offset({"candidate_summary_by_command":{"charge":[],"discharge":[p]}},
                                    {"candidate_summary_by_command":{"charge":[],"discharge":[q]}})
        self.assertFalse(x["offset_inferred"])

    def test_nonfinite_rows_not_used(self):
        dat=synth_zip()
        # Insert invalid numeric sample, still keep good data.
        with zipfile.ZipFile(io.BytesIO(dat)) as z:
            txt=z.read("F0001/M0001_checkup.txt").decode()
        txt=txt.replace("0.5,2,", "0.25,99,0.25,0.25,17,Discharge,3.5,nan,0,0,0,1,1\n0.5,2,")
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr("F0001/M0001_checkup.txt",txt)
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            q=m.scan_checkup(z,"F0001/M0001_checkup.txt")
        self.assertEqual(q["rows_parsed"],6)

if __name__=="__main__":
    unittest.main()