"""Apply guarded, repeatable local fixes to OpenMM 8.6.1's Python parser/writer."""
import difflib
from pathlib import Path
import openmm.app.pdbxfile as module

path=Path(module.__file__)
backup=path.with_suffix('.py.original')
old=backup.read_text() if backup.exists() else path.read_text()
new=old
for before, after, count in [
    ("chr(ord('A')+chainIndex%26)", "('C'+str(chainIndex+1))", 2),
    ("atomTable = {}", "atomTable = {}\n        alternateTable = {}", 1),
    ("atomKey = ((row[resIdCol], row[chainIdCol], row[atomNameCol]))",
     "atomKey = ((row[resIdCol], row[chainIdCol], row[atomNameCol]))\n            alternateKey = (row[resIdCol], row[chainIdCol], row[resNumCol], (row[resInsertionCol] if resInsertionCol != -1 else ''), row[atomNameCol])", 1),
    ("atomKey in atomTable and len(self._positions[modelIndex]) > atomTable[atomKey].index",
     "alternateKey in alternateTable and len(self._positions[modelIndex]) > alternateTable[alternateKey].index", 1),
    ("atomTable[atomKey] = atom", "atomTable[atomKey] = atom\n                alternateTable[alternateKey] = atom", 1),
    ("atom = atomTable[atomKey]", "atom = alternateTable[alternateKey]", 1),
]:
    if new.count(before)!=count:
        raise RuntimeError(f'Unexpected source; refusing patch: {before}')
    new=new.replace(before, after)
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/openmm/app/pdbxfile.py',tofile='b/openmm/app/pdbxfile.py'))
Path(__file__).with_name('mmcif_fixes.patch').write_text(patch)
backup.write_text(old)
path.write_text(new)
print(f'Patched {path}; original backed up. Restart Python before testing.')
