import unittest
import numpy as np
from common_loss import fit, predict

class CommonLossTest(unittest.TestCase):
    def test_symmetric_loss(self):
        g=np.full(100,800.)
        b=fit(g,np.full(100,1600.),np.full(100,1600.))
        status=predict(b,np.array([800.,800.,800.,800.,100.,900.]),np.array([1600.,960.,0.,960.,0.,0.]),np.array([1600.,960.,0.,1600.,0.,0.]))
        self.assertEqual(status.tolist(),['NO_COMMON_LOW','COMMON_LOW','COMMON_LOW','NO_COMMON_LOW','UNAVAILABLE','UNAVAILABLE'])
    def test_negative_and_nonfinite(self):
        b=fit(np.full(100,800.),np.full(100,1600.),np.full(100,1600.))
        self.assertEqual(predict(b,np.array([800.,800.]),np.array([-1.,np.nan]),np.array([0.,0.])).tolist(),['UNAVAILABLE','UNAVAILABLE'])
if __name__=='__main__':unittest.main()
