# Reproducer from https://github.com/openmm/openmm/issues/5493 by RedesignedRobot.
"""A Context that loads a checkpoint should continue exactly like the Context that wrote it.

Water box with PME, and DeterministicForces on platforms that have the property (OpenCL always
accumulates forces in fixed point). After 50 steps, writes a checkpoint after each of 20 steps, loads it
into a new Context and compares forces bitwise. Then writes one more checkpoint, runs both
Contexts 100 steps and compares positions. Runs once with VerletIntegrator and once with a velocity
Verlet CustomIntegrator, which reuses the forces from the end of the previous step.

usage: python checkpoint_repro.py [platform] [precision]     (default OpenCL single)
"""
import io
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
                system.addConstraint(o, o+1, 0.09572)
                system.addConstraint(o, o+2, 0.09572)
                system.addConstraint(o+1, o+2, 0.15139)
                bonds += [(o, o+1), (o, o+2)]
    nb.createExceptionsFromBonds(bonds, 0.0, 0.0)
    return system, np.array(positions)


def integrator(custom):
    if not custom:
        return mm.VerletIntegrator(0.002)
    i = mm.CustomIntegrator(0.002)
    i.addPerDofVariable("x1", 0)
    i.addUpdateContextState()
    i.addComputePerDof("v", "v+0.5*dt*f/m")
    i.addComputePerDof("x", "x+dt*v")
    i.addComputePerDof("x1", "x")
    i.addConstrainPositions()
    i.addComputePerDof("v", "v+0.5*dt*f/m+(x-x1)/dt")
    i.addConstrainVelocities()
    return i


def get(context):
    s = context.getState(getPositions=True, getForces=True)
    return s.getPositions(asNumpy=True).value_in_unit(u.nanometer), s.getForces(asNumpy=True).value_in_unit(u.kilojoule_per_mole/u.nanometer)


def run(system, positions, platform, props, custom):
    integ = integrator(custom)
    context = mm.Context(system, integ, platform, props)
    context.setPositions(positions)
    context.setVelocitiesToTemperature(300, 5)
    integ.step(50)
    differ = []
    for step in range(1, 21):
        integ.step(1)
        checkpoint = context.createCheckpoint()
        integ2 = integrator(custom)
        context2 = mm.Context(system, integ2, platform, props)
        context2.loadCheckpoint(checkpoint)
        (x1, f1), (x2, f2) = get(context), get(context2)
        if not (np.array_equal(x1, x2) and np.array_equal(f1, f2)):
            differ.append((step, np.max(np.abs(f1 - f2))))
        del context2
    integ.step(1)
    checkpoint = context.createCheckpoint()
    integ2 = integrator(custom)
    context2 = mm.Context(system, integ2, platform, props)
    context2.loadCheckpoint(checkpoint)
    integ.step(100)
    integ2.step(100)
    (x1, f1), (x2, f2) = get(context), get(context2)
    return differ, np.max(np.abs(x1 - x2))


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "OpenCL"
    precision = sys.argv[2] if len(sys.argv) > 2 else "single"
    platform = mm.Platform.getPlatformByName(name)
    props = {"Precision": precision}
    if "DeterministicForces" in platform.getPropertyNames():
        props["DeterministicForces"] = "true"
    system, positions = water_box()
    print(f"OpenMM {mm.version.git_revision}, {name} {precision}, {props}, {system.getNumParticles()} atoms")
    for custom in (False, True):
        differ, dx = run(system, positions, platform, props, custom)
        label = "CustomIntegrator (velocity Verlet)" if custom else "VerletIntegrator"
        print(f"{label}: forces differ after loading at {len(differ)} of 20 checkpoints"
              + (f" (first at step {differ[0][0]}, max|dF| {max(d for _, d in differ):.6g} kJ/mol/nm)" if differ else "")
              + f"; after 100 more steps max|dx| {dx:.6g} nm")
