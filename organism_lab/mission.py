"""A bounded virtual mission that combines robots and digital organisms."""
from .robot_factory import RobotFactory
from .evolution import World
from .core import grid_route

def run_mission(*, steps=10, resources=12, parts_per_kind=3, width=5, height=5):
    if not isinstance(steps, int) or not 0 <= steps <= 10000:
        raise ValueError("Invalid step count")
    if not isinstance(parts_per_kind, int) or parts_per_kind < 0:
        raise ValueError("Invalid inventory")
    factory = RobotFactory(parts={p: parts_per_kind for p in RobotFactory.REQUIRED},
                           max_robots=max(1, parts_per_kind))
    founder = factory.assemble()
    world = World(resources=resources)
    history = []
    for tick in range(steps):
        robot = factory.replicate(founder.identifier) if founder is not None else None
        path = grid_route(width, height, (0, 0), (width - 1, height - 1))
        organisms = world.step()
        history.append({"tick": tick + 1, "robots": len(factory.robots),
                        "robot_created": robot is not None, "route_length": len(path) if path else None,
                        "organism_population": organisms["population"],
                        "organism_births": organisms["births"]})
    return {"history": history, "robot_metrics": factory.metrics(),
            "organism_metrics": world.metrics()}
