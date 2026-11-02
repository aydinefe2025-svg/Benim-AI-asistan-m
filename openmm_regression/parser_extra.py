"""Check alternate waters in two models, including preservation of the first conformer."""
import io
from pathlib import Path
import numpy as np
from openmm.app import PDBxFile
from openmm import unit
text=Path('waters.cif').read_text()
lines=text.splitlines()
second=[]
for line in lines:
    if line.startswith(('ATOM','HETATM')):
        tokens=line.split()
        tokens[-1]='2'
        tokens[10]=str(float(tokens[10])+10)
        second.append(' '.join(tokens))
combined=text.rstrip().rstrip('#')+'\n'+'\n'.join(second)+'\n#\n'
p=PDBxFile(io.StringIO(combined))
assert p.getNumFrames()==2
assert p.topology.getNumAtoms()==7
a=p.getPositions(asNumpy=True,frame=0).value_in_unit(unit.nanometer)
b=p.getPositions(asNumpy=True,frame=1).value_in_unit(unit.nanometer)
assert np.allclose(b-a, np.array([1,0,0]))
assert [r.id for r in p.topology.residues() if r.name=='HOH']==['101','102','103']
print('PASS: two-model alternate-water identities, first conformers and coordinates')
