from enum import Enum


class Scope(Enum):
    SINGLETON = 'singleton'
    SCOPED = 'scoped'
    TRANSIENT = 'transient'
