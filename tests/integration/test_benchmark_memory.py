import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, is_object, memory, work

ROOT = Path(__file__).resolve().parents[2]


def _outer() -> int:
    return _inner() + _inner()


def _inner() -> int:
    return 1


ALLOCATION_PROBE = """
import json, sys

from benchmarks.harness import HarnessError, memory

def build():
    return [object() for _ in range(64)]

try:
    counted = memory.allocations_per_operation(build, operations=1)
    held = memory.retained(build)
except HarnessError as error:
    json.dump({'error': str(error)}, sys.stdout)
else:
    json.dump({'blocks': counted.blocks, 'size': counted.size, 'peak': counted.peak, 'retained': held}, sys.stdout)
"""


def _probe(source: str, *, hash_seed: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, '-c', source],
        cwd=ROOT,
        env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT), 'PYTHONHASHSEED': hash_seed},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    decoded: object = json.loads(completed.stdout)
    assert is_object(decoded)
    return decoded


def test_python_calls_are_counted_per_operation() -> None:
    assert work.calls_per_operation(_outer, operations=100) == 3


def test_a_workload_whose_call_count_varies_is_reported_rather_than_averaged() -> None:
    counter = {'calls': 0}

    def alternating() -> None:
        counter['calls'] += 1
        if counter['calls'] % 2 == 0:
            _ = _inner()

    with pytest.raises(HarnessError, match='does not divide evenly'):
        _ = work.calls_per_operation(alternating, operations=3)


def test_counting_calls_needs_at_least_one_operation() -> None:
    with pytest.raises(HarnessError, match='at least one'):
        _ = work.calls_per_operation(_outer, operations=0)


def test_allocations_are_measured_under_a_fixed_hash_seed() -> None:
    measured = _probe(ALLOCATION_PROBE, hash_seed=memory.HASH_SEED)

    assert 'error' not in measured
    assert isinstance(measured['blocks'], int)
    assert measured['blocks'] > 0
    assert isinstance(measured['retained'], int)
    assert measured['retained'] > 0


def test_allocation_measurement_refuses_a_randomised_hash_seed() -> None:
    """The seed cannot be set after start, so the guard is the only place this is catchable."""
    measured = _probe(ALLOCATION_PROBE, hash_seed='1')

    assert 'PYTHONHASHSEED' in str(measured['error'])
