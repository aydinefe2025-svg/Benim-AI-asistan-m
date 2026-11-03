"""Keep NVIDIA wheel DLL directories available for Windows native plugin loading."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]
p=root/'.venv/Lib/site-packages/openmm/__init__.py'
text=p.read_text()
marker='# Local CUDA wheel DLL discovery'
hook='''# Local CUDA wheel DLL discovery
_nvidia_dll_handles = []
_nvidia_dll_paths = []
if sys.platform == 'win32':
    _nvidia_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'nvidia'))
    if os.path.isdir(_nvidia_root):
        for _component in sorted(os.listdir(_nvidia_root)):
            for _subdir in ('bin', 'lib'):
                _directory = os.path.join(_nvidia_root, _component, _subdir)
                if os.path.isdir(_directory):
                    _nvidia_dll_handles.append(os.add_dll_directory(_directory))
                    _nvidia_dll_paths.append(_directory)
    # OpenMM's C++ loader uses LoadLibrary, and cuFFT also loads JIT DLLs later.
    # Keep these paths available in this Python process, without changing the
    # user's persistent PATH or requiring a system CUDA Toolkit installation.
    os.environ['PATH'] = ';'.join(_nvidia_dll_paths + [os.environ.get('PATH', '')])

'''
if marker in text:
    start=text.index(marker)
    end=text.index("if sys.platform == 'win32':\n    _path",start)
    p.write_text(text[:start]+hook+text[end:])
else:
    before="if sys.platform == 'win32':\n"
    assert before in text
    p.with_name('__init__.py.stock').write_text(text)
    p.write_text(text.replace(before,hook+before,1))
print('NVIDIA DLL discovery ready')
