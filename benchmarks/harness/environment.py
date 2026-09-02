"""The host, interpreter and distribution metadata recorded beside every measurement.

Every absolute figure the project publishes is host-specific, and the only thing
that makes it readable rather than misleading is the host it was measured on being
recorded next to it. What transfers between hosts is the ratio to a direct
baseline, the complexity class, and the deterministic counts; this module is what
lets a reader tell those apart from the rest.
"""

import os
import pathlib
import platform
import sys
import sysconfig
from importlib import metadata

RECORDED_DISTRIBUTIONS = ('pydepin', 'pytest', 'pytest-benchmark')


def _load_average() -> list[float] | None:
    """The one-, five- and fifteen-minute load, where the platform reports it.

    Recorded rather than gated. The project does not own a quiet benchmark
    machine, so the load a dataset was measured under is part of the dataset.
    """
    if not hasattr(os, 'getloadavg'):
        return None
    return [round(value, 2) for value in os.getloadavg()]


def _cpu_model() -> str | None:
    """The CPU's marketing name, where the platform exposes one.

    `platform.processor()` answers `x86_64` on Linux, which names an instruction
    set rather than a machine. An absolute microsecond figure is only readable
    against the chip that produced it, so the model is read from
    ``/proc/cpuinfo`` where that exists and left absent where it does not.
    """
    try:
        contents = pathlib.Path('/proc/cpuinfo').read_text(encoding='utf-8')
    except OSError:
        return None
    for line in contents.splitlines():
        field, separator, value = line.partition(':')
        if separator and field.strip() == 'model name':
            return value.strip()
    return None


def _available_processors() -> int | None:
    if not hasattr(os, 'sched_getaffinity'):
        return None
    return len(os.sched_getaffinity(0))


def _distributions() -> dict[str, object]:
    versions: dict[str, object] = {}
    for name in RECORDED_DISTRIBUTIONS:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def capture() -> dict[str, object]:
    """Everything about this process a published number depends on.

    The result is JSON-serialisable and carries no path, so a dataset can be
    committed without carrying the layout of the machine that produced it.
    """
    interpreter: dict[str, object] = {
        'implementation': platform.python_implementation(),
        'version': platform.python_version(),
        'compiler': platform.python_compiler(),
        'free_threading': bool(sysconfig.get_config_var('Py_GIL_DISABLED')),
        'hash_randomization': bool(sys.flags.hash_randomization),
        'recursion_limit': sys.getrecursionlimit(),
    }
    host: dict[str, object] = {
        'system': platform.system(),
        'release': platform.release(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'cpu_model': _cpu_model(),
        'processors': os.cpu_count(),
        'available_processors': _available_processors(),
        'load_average': _load_average(),
    }
    return {'interpreter': interpreter, 'host': host, 'distributions': _distributions()}
