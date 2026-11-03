"""Build the patched OpenMM native libraries with MSVC and local Khronos SDK."""
from pathlib import Path
import os, subprocess, sys, shutil
root=Path(__file__).resolve().parents[2]
cmake=root/'.venv/Lib/site-packages/cmake/data/bin/cmake.exe'
ninja=root/'.venv/Scripts/ninja.exe'
vcvars=r'C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Auxiliary/Build/vcvars64.bat'
r=subprocess.run(f'call "{vcvars}" >nul && set',shell=True,capture_output=True,text=True)
if r.returncode: raise RuntimeError(r.stderr)
env=os.environ.copy()
for line in r.stdout.splitlines():
    if '=' in line and not line.startswith('='):
        k,v=line.split('=',1);env[k.upper()]=v
sdk=Path('C:/Program Files (x86)/Windows Kits/10')
sdk_version='10.0.26100.0'
sdk_bin=sdk/'bin'/sdk_version/'x64'
env['PATH']=str(sdk_bin)+';'+env['PATH']
env['INCLUDE']=';'.join(str(sdk/'Include'/sdk_version/x) for x in ('ucrt','shared','um','winrt'))+';'+env.get('INCLUDE','')
env['LIB']=';'.join(str(sdk/'Lib'/sdk_version/x/'x64') for x in ('ucrt','um'))+';'+env.get('LIB','')
logs=root/'repo/openmm_regression/native_results'
logs.mkdir(exist_ok=True)
def run(name,args):
    print(name,flush=True)
    with (logs/(name+'.log')).open('w') as out:
        args=list(args)
        if '-S' in args:
            args += ['-DCMAKE_RC_COMPILER='+(sdk_bin/'rc.exe').as_posix(),'-DCMAKE_MT='+(sdk_bin/'mt.exe').as_posix()]
        args=[str(a).replace('\\','/') if str(a).startswith('-D') else str(a) for a in args]
        p=subprocess.run([str(cmake),*map(str,args)],cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    print((logs/(name+'.log')).read_text(errors='replace')[-2200:],flush=True)
    if p.returncode: raise SystemExit(p.returncode)
opts=['-S','openmm-source','-B','native-build','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_MAKE_PROGRAM={ninja}',f'-DPYTHON_EXECUTABLE={sys.executable}',f'-DOPENCL_INCLUDE_DIR={root/"opencl-headers"}',f'-DOPENCL_LIBRARY={root/"opencl-build/OpenCL.lib"}',f'-DCMAKE_INSTALL_PREFIX={root/"native-install"}','-DOPENMM_BUILD_OPENCL_LIB=ON','-DOPENMM_BUILD_CUDA_LIB=OFF','-DOPENMM_BUILD_HIP_LIB=OFF','-DOPENMM_BUILD_PYTHON_WRAPPERS=OFF','-DOPENMM_BUILD_C_AND_FORTRAN_WRAPPERS=OFF','-DOPENMM_BUILD_AMOEBA_PLUGIN=ON','-DOPENMM_BUILD_DRUDE_PLUGIN=ON','-DOPENMM_BUILD_RPMD_PLUGIN=ON','-DOPENMM_BUILD_PME_PLUGIN=ON','-DBUILD_TESTING=ON','-DOPENMM_BUILD_REFERENCE_TESTS=OFF','-DOPENMM_BUILD_SERIALIZATION_TESTS=OFF','-DOPENMM_BUILD_CPU_TESTS=ON','-DOPENMM_BUILD_OPENCL_TESTS=ON','-DCMAKE_POLICY_VERSION_MINIMUM=3.5']
if __name__ == '__main__':
    shutil.copy2(root/'opencl-clhpp/include/CL/opencl.hpp',root/'opencl-headers/CL/opencl.hpp')
    run('loader_configure',['-S','opencl-loader','-B','opencl-build','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_MAKE_PROGRAM={ninja}',f'-DOPENCL_ICD_LOADER_HEADERS_DIR={root/"opencl-headers"}','-DBUILD_TESTING=OFF','-DENABLE_OPENCL_LAYERS=OFF'])
    run('loader_build',['--build','opencl-build','--parallel','4'])
    run('openmm_configure',opts)
    run('openmm_build',['--build','native-build','--target','OpenMM','OpenMMCPU','OpenMMOpenCL','OpenMMPME','OpenMMAmoeba','OpenMMAmoebaReference','OpenMMAmoebaOpenCL','OpenMMDrude','OpenMMDrudeReference','OpenMMDrudeOpenCL','OpenMMRPMD','OpenMMRPMDReference','OpenMMRPMDOpenCL','--parallel','4'])
    run('native_test_build',['--build','native-build','--target','TestCpuNeighborList','TestCpuNonbondedForce','TestCpuPme','TestOpenCLCheckpoints','TestOpenCLNonbondedForce','TestOpenCLEwald','--parallel','4'])
    run('openmm_install',['--install','native-build'])

