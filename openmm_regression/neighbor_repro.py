# Reproducer from https://github.com/openmm/openmm/issues/5515 by hikarino-my.
import numpy as np
import openmm
from openmm import unit

L = 5.0

def pair_count(platform, bx, x0, eps, n=4000):
    """Number of pairs within the cutoff (energy 1 per pair) for n random particles in a box with b = (bx, L, 0).
    Particle 0 is placed at y = L - eps, just below the y face."""
    rng = np.random.default_rng(0)
    pos = rng.random((n, 3)) * L
    pos[0] = (x0, L - eps, 2.5)
    force = openmm.CustomNonbondedForce("1")
    force.setNonbondedMethod(openmm.CustomNonbondedForce.CutoffPeriodic)
    force.setCutoffDistance(1.0)
    system = openmm.System()
    for _ in range(n):
        system.addParticle(1.0)
        force.addParticle([])
    system.setDefaultPeriodicBoxVectors(openmm.Vec3(L, 0, 0), openmm.Vec3(bx, L, 0), openmm.Vec3(0, 0, L))
    system.addForce(force)
    context = openmm.Context(system, openmm.VerletIntegrator(0.001), openmm.Platform.getPlatformByName(platform))
    context.setPositions(pos * unit.nanometer)
    return round(context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole))

for bx in (0.0, 1.5, -1.5):
    for eps in (1e-5, 1e-8):
        missing = [pair_count("Reference", bx, x0, eps) - pair_count("CPU", bx, x0, eps) for x0 in (0.5, 1.5, 2.5, 3.5, 4.5)]
        print(f"b_x = {bx:4g}  y0 = L - {eps:.0e}  (float32(y0) == float32(L): {np.float32(L - eps) == np.float32(L)}):  "
              f"pairs missing on CPU for x0 = 0.5, 1.5, 2.5, 3.5, 4.5: {missing}")
