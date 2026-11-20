import importlib.util,unittest,math,tempfile,json,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
spec=importlib.util.spec_from_file_location('f85', Path(__file__).with_name('f85_native_heldout_replay.py'))
f85=importlib.util.module_from_spec(spec);spec.loader.exec_module(f85)

class ActualNativeSupportFormula(unittest.TestCase):
  def setUp(self):
    self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
    root=Path(self.temp.name)
    self.npz=root/'real_fixture.npz';self.jsonl=root/'real_fixture.jsonl'
    self.z=np.zeros((2048,13),dtype=float)
    self.base=-.5*13*math.log(2*math.pi)
    self.support=np.linspace(-.5,.5,2048)
    self.logq=np.linspace(-1.,1.,2048)
    self.logL=np.full(2048,-21900.,dtype=float)
    self.logL[932]=-21897.
    self.logw=self.logL+self.base-self.support-self.logq
    np.savez(self.npz,z=self.z,logweights=self.logw)
    rows=[{'index':i,'z':self.z[i].tolist(),'logL':float(self.logL[i]),'logq':float(self.logq[i]),'log_nuisance_support':float(self.support[i])} for i in range(2048)]
    self.rows=rows
    self.jsonl.write_text('\n'.join(json.dumps(row) for row in rows)+'\n',encoding='utf8')
    w=np.exp(self.logw-logsumexp(self.logw))
    self.report={'npz_sha256':hashlib.sha256(self.npz.read_bytes()).hexdigest(),'jsonl_sha256':hashlib.sha256(self.jsonl.read_bytes()).hexdigest(),'top_samples':[{'index':int(np.argmax(w))}], 'independently_reconstructed':{'ESS':float(1/np.dot(w,w)),'max_weight_fraction':float(w.max())}}
  def test_support_term_is_actually_applied_to_each_real_row(self):
    r=f85.raw_replay(self.npz,self.jsonl,self.report,support_field='log_nuisance_support')
    self.assertEqual(r['status'],'BYTE_VERIFIED_REAL_RAW_REPLAY_PASS')
    self.assertEqual(r['support_correction_status'],'APPLIED_TO_ALL_FINITE_LIKELIHOODS')
  def test_source_nuisance_support_field_cannot_be_silently_skipped(self):
    with self.assertRaises(f85.SourceError):f85.raw_replay(self.npz,self.jsonl,self.report)
  def test_wrong_formula_must_fail_instead_of_accepting_raw(self):
    for row in self.rows:row['log_nuisance_support']=0.0
    self.jsonl.write_text('\n'.join(json.dumps(row) for row in self.rows)+'\n',encoding='utf8')
    self.report['jsonl_sha256']=hashlib.sha256(self.jsonl.read_bytes()).hexdigest()
    with self.assertRaises(f85.SourceError):f85.raw_replay(self.npz,self.jsonl,self.report,support_field='log_nuisance_support')
  def test_missing_support_in_just_one_finite_event_is_hard_failure(self):
    del self.rows[932]['log_nuisance_support']
    self.jsonl.write_text('\n'.join(json.dumps(row) for row in self.rows)+'\n',encoding='utf8')
    self.report['jsonl_sha256']=hashlib.sha256(self.jsonl.read_bytes()).hexdigest()
    with self.assertRaises(f85.SourceError):f85.raw_replay(self.npz,self.jsonl,self.report,support_field='log_nuisance_support')
if __name__=='__main__': unittest.main()
