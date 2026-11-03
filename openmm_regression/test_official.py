"""Run the built upstream CPU/OpenCL test programs with the local native install."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parents[2]
env=os.environ.copy()
env['OPENMM_PLUGIN_DIR']=str(root/'native-install/lib/plugins')
cuda_dirs=[str(p) for p in (root/'.venv/Lib/site-packages/nvidia').glob('*/bin') if p.is_dir()]
env['PATH']=';'.join([str(root/'native-install/lib'),*cuda_dirs,env.get('PATH','')])
ctest=root/'.venv/Lib/site-packages/cmake/data/bin/ctest.exe'
pattern=r'^(TestCpuNeighborList|TestCpuNonbondedForce|TestCpuPme|Test(OpenCL|Cuda)(Checkpoints|NonbondedForce|Ewald)(Single|Mixed|Double))$'
r=subprocess.run([str(ctest),'--test-dir',str(root/'native-build'),'-R',pattern,'--output-on-failure','--timeout','240','-j','2'],env=env,text=True,capture_output=True)
(Path(__file__).parent/'native_results/official_tests.log').write_text(r.stdout+'\nSTDERR:\n'+r.stderr)
print(r.stdout,r.stderr)
raise SystemExit(r.returncode)
