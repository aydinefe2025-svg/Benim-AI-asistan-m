"""Build patched CUDA plugins using the pinned official NVIDIA Python wheels."""
from pathlib import Path
import json
import re
import shutil
import subprocess
from build_native import root, env, run, opts

packages=root/'.venv/Lib/site-packages/nvidia'
sdk=root/'cuda-sdk'
for directory in ('bin','include','lib/x64'):
    (sdk/directory).mkdir(parents=True,exist_ok=True)
for name in ('cuda_runtime','cuda_nvcc','cuda_nvrtc','cuda_cupti','cuda_profiler_api','cufft','nvjitlink'):
    component=packages/name
    if name=='nvjitlink' and not component.is_dir():
        continue  # Not linked at build time; required before runtime validation.
    assert component.is_dir(),f'Missing pinned NVIDIA component: {name}'
    for directory in ('bin','include','nvvm'):
        if (component/directory).is_dir():
            shutil.copytree(component/directory,sdk/directory,dirs_exist_ok=True)
(sdk/'version.json').write_text(json.dumps({'cuda':{'name':'CUDA components from official NVIDIA wheels','version':'12.6.85'}}))
tools=Path('C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/bin/Hostx64/x64')
def import_library(name,dll):
    exports=subprocess.check_output([str(tools/'dumpbin.exe'),'/exports',str(dll)],text=True,errors='replace')
    symbols=[]
    for line in exports.splitlines():
        m=re.match(r'^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)',line)
        if m: symbols.append(m.group(1))
    assert symbols,f'No exports in {dll}'
    definition=sdk/'lib/x64'/f'{name}.def'
    definition.write_text('LIBRARY '+dll.name+'\nEXPORTS\n'+'\n'.join(symbols)+'\n')
    subprocess.run([str(tools/'lib.exe'),'/nologo','/machine:x64',f'/def:{definition}',f'/out:{sdk/"lib/x64"/(name+".lib")}'],env=env,check=True)
for name,file in [('cudart','cudart64_12.dll'),('nvrtc','nvrtc64_120_0.dll'),('cufft','cufft64_11.dll')]:
    import_library(name,sdk/'bin'/file)
import_library('cuda',Path('C:/Windows/System32/nvcuda.dll'))
env['CUDA_PATH']=str(sdk)
env['PATH']=str(sdk/'bin')+';'+env['PATH']
cuda_opts=[x for x in opts if x!='-DOPENMM_BUILD_CUDA_LIB=OFF']
cuda_opts += ['-DOPENMM_BUILD_CUDA_LIB=ON',f'-DCUDAToolkit_ROOT={sdk}','-DOPENMM_BUILD_CUDA_TESTS=ON']
cuda_opts += [f'-DOPENMM_BUILD_{name}_CUDA_LIB=ON' for name in ('AMOEBA','DRUDE','RPMD')]
run('cuda_configure',cuda_opts)
run('cuda_build',['--build','native-build','--target','OpenMMCUDA','OpenMMAmoebaCUDA','OpenMMDrudeCUDA','OpenMMRPMDCUDA','TestCudaCheckpoints','TestCudaNonbondedForce','TestCudaEwald','--parallel','4'])
run('cuda_install',['--install','native-build'])
