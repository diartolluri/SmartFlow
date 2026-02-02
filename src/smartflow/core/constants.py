from enum import Enum

class DistributionType(str, Enum):
    UNIFORM = "uniform"
    LOGNORMAL = "lognormal"
    NORMAL = "normal"
    FIXED = "value"

class AgentState(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    FINISHED = "finished"
    STUCK = "stuck"
