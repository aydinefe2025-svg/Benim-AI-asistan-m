"""Synthetic regression checks for OpenMM issues #5532 and #5521."""
import argparse
import io
import json
from pathlib import Path

import numpy as np
from openmm import Vec3, unit
from openmm.app import PDBxFile, Topology, element


def roundtrip(n, keep_ids=False):
    top = Topology()
    atoms = []
    for i in range(n):
        chain = top.addChain(f'C{i}')
        res = top.addResidue('LIG', chain, '1')
        atoms.append(top.addAtom('C', element.carbon, res))
    expected = {(0, n-1)}
    top.addBond(atoms[0], atoms[-1])
    stream = io.StringIO()
    positions = [Vec3(i*0.1, 0, 0) for i in range(n)]*unit.nanometer
    PDBxFile.writeFile(top, positions, stream, keepIds=keep_ids)
    parsed = PDBxFile(io.StringIO(stream.getvalue()))
    chains = list(parsed.topology.chains())
    bonds = {tuple(sorted((a.index, b.index))) for a,b in parsed.topology.bonds()}
    checks = dict(atoms=parsed.topology.getNumAtoms()==n,
                  chains=len(chains)==n, unique_ids=len({c.id for c in chains})==n,
                  bonds=bonds==expected, no_self_bonds=all(a!=b for a,b in bonds),
                  positions=np.allclose(parsed.positions.value_in_unit(unit.nanometer), positions.value_in_unit(unit.nanometer), atol=1e-8))
    return dict(issue=5532, chains=n, keep_ids=keep_ids,
                status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                observed_bonds=sorted(bonds))


def waters():
    parsed = PDBxFile(str(Path(__file__).parent/'waters.cif'))
    residues = [r for r in parsed.topology.residues() if r.name=='HOH']
    ids = [r.id for r in residues]
    coords = parsed.positions.value_in_unit(unit.nanometer)
    ok = ids==['101','102','103'] and len(coords)==7
    if ok:
        ok = np.allclose(coords[-3:], [[.5,0,0],[0,.5,0],[0,0,.5]])
    return dict(issue=5521, status='PASS' if ok else 'FAIL', water_ids=ids, atoms=len(coords))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', default='mmcif_results.json')
    args=parser.parse_args()
    results=[roundtrip(n, keep) for keep in (False, True) for n in (26,27,52)] + [waters()]
    Path(args.output).write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
    raise SystemExit(any(r['status']=='FAIL' for r in results))
