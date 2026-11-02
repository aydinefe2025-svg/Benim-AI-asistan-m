# Reproducer from https://github.com/openmm/openmm/issues/5494 by RedesignedRobot.
"""UseCpuPme=true has no effect on GPU platforms.

Builds a 4 nm PME water box, then computes forces on one platform three times: twice with GPU PME
(UseCpuPme=false) and once with UseCpuPme=true. The CPU PME plugin uses its own grid code, so if it ran,
its forces would differ from GPU PME at the level of PME's error. It also prints the Reference platform's
error for each, and whether the platform reports the CPU PME kernel as available.

usage: python cpupme_repro.py [platform] [precision]     (default OpenCL single)
"""
import math
import sys

import numpy as np
import openmm as mm
import openmm.unit as u


def water_box(n=13, box=4.0):
    system = mm.System()
    system.setDefaultPeriodicBoxVectors(mm.Vec3(box, 0, 0), mm.Vec3(0, box, 0), mm.Vec3(0, 0, box))
    nb = mm.NonbondedForce()
    nb.setNonbondedMethod(mm.NonbondedForce.PME)
    nb.setCutoffDistance(0.9)
    nb.setEwaldErrorTolerance(5e-4)
    system.addForce(nb)
    positions, bonds = [], []
    angle = 104.52*math.pi/180
    d = box/n
    for i in range(n):
        for j in range(n):
            for k in range(n):
                o = system.addParticle(15.999)
                system.addParticle(1.008)
                system.addParticle(1.008)
                nb.addParticle(-0.834, 0.31507524, 0.635968)
                nb.addParticle(0.417, 1.0, 0.0)
                nb.addParticle(0.417, 1.0, 0.0)
                p = np.array([i*d, j*d, k*d])
                positions += [p, p + [0.09572, 0, 0], p + [0.09572*math.cos(angle), 0.09572*math.sin(angle), 0]]
                bonds += [(o, o+1), (o, o+2)]
    nb.createExceptionsFromBonds(bonds, 0.0, 0.0)
    return system, np.array(positions)


def forces(system, positions, name, props):
    context = mm.Context(system, mm.VerletIntegrator(0.001), mm.Platform.getPlatformByName(name), props)
    context.setPositions(positions)
    state = context.getState(getForces=True, getEnergy=True)
    return (state.getForces(asNumpy=True).value_in_unit(u.kilojoule_per_mole/u.nanometer),
            state.getPotentialEnergy().value_in_unit(u.kilojoule_per_mole))


if __name__ == "__main__":
    platform_name = sys.argv[1] if len(sys.argv) > 1 else "OpenCL"
    precision = sys.argv[2] if len(sys.argv) > 2 else "single"
    system, positions = water_box()
    print(f"OpenMM {mm.version.git_revision}, {platform_name} {precision}, {system.getNumParticles()} atoms")
    platform = mm.Platform.getPlatformByName(platform_name)
    print(f"{platform_name} supports CalcPmeReciprocalForce (the CPU PME plugin is loaded): "
          f"{platform.supportsKernels(['CalcPmeReciprocalForce'])}")
    ref, e_ref = forces(system, positions, "Reference", {})
    gpu1, e1 = forces(system, positions, platform_name, {"Precision": precision, "UseCpuPme": "false"})
    gpu2, e2 = forces(system, positions, platform_name, {"Precision": precision, "UseCpuPme": "false"})
    cpu, e3 = forces(system, positions, platform_name, {"Precision": precision, "UseCpuPme": "true"})
    rms = np.sqrt(np.mean(ref**2))
    print(f"energy kJ/mol: Reference {e_ref:.4f}, GPU PME {e1:.4f}, GPU PME again {e2:.4f}, UseCpuPme=true {e3:.4f}")
    print(f"GPU PME vs GPU PME again:  max|dF| {np.max(np.abs(gpu1 - gpu2)):.6e}")
    print(f"GPU PME vs UseCpuPme=true: max|dF| {np.max(np.abs(gpu1 - cpu)):.6e}")
    print(f"vs Reference, max|dF|/rms: GPU PME {np.max(np.abs(gpu1 - ref))/rms:.6e}, "
          f"UseCpuPme=true {np.max(np.abs(cpu - ref))/rms:.6e}")
    print("UseCpuPme=true forces are bitwise equal to GPU PME" if np.array_equal(gpu1, cpu)
          else "UseCpuPme=true forces differ from GPU PME")
