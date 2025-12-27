from enum import Enum, auto

class ProcessState(Enum):
    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    TERMINATING = auto()
    TERMINATED = auto()
    FAILED = auto()
    TIMEOUT = auto()
