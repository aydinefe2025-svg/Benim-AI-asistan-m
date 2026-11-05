"""Resource-bounded virtual modular robot assembly; no hardware actuation."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Robot:
    identifier: int
    parent: int | None
    generation: int
    modules: tuple[str, ...]

class RobotFactory:
    REQUIRED = ("controller", "power", "sensor", "wheel")

    def __init__(self, *, parts=None, max_robots=8):
        if max_robots < 1:
            raise ValueError("max_robots must be positive")
        self.parts = dict(parts if parts is not None else {part: 4 for part in self.REQUIRED})
        if any(v < 0 or not isinstance(v, int) for v in self.parts.values()):
            raise ValueError("Parts must be nonnegative integers")
        self.max_robots = max_robots
        self.robots = {}
        self.next_id = 0

    def assemble(self, parent=None):
        if parent is not None and parent not in self.robots:
            raise KeyError("Unknown parent robot")
        if len(self.robots) >= self.max_robots:
            return None
        if any(self.parts.get(part, 0) < 1 for part in self.REQUIRED):
            return None
        for part in self.REQUIRED:
            self.parts[part] -= 1
        generation = self.robots[parent].generation + 1 if parent is not None else 0
        robot = Robot(self.next_id, parent, generation, self.REQUIRED)
        self.robots[robot.identifier] = robot
        self.next_id += 1
        return robot

    def replicate(self, parent):
        """Construct another robot from external inventory; no self-manufacturing."""
        return self.assemble(parent=parent)

    def metrics(self):
        return {"robots": len(self.robots), "available_parts": dict(self.parts),
                "max_generation": max((r.generation for r in self.robots.values()), default=0)}
