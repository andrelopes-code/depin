"""The measured cold-resolution recursion-depth cliff."""

import json
import os
import subprocess
import sys
from pathlib import Path

from benchmarks.harness import HarnessError, is_object, require_integer, require_object

DEPTH_CLIFF = 332


FRAMES_PER_PROVIDER = 3


CLIFF_PROBE = """
import json
import sys

from benchmarks.graphs import build_chain
from depin import Scope

deepest = {}
for scope in (Scope.SINGLETON, Scope.TRANSIENT):
    low, high, best = 1, 900, 0
    while low <= high:
        middle = (low + high) // 2
        container, leaf = build_chain(middle, scope=scope)
        frozen = container.freeze()
        try:
            frozen.resolve(leaf)
        except RecursionError:
            high = middle - 1
        else:
            best = middle
            low = middle + 1
    deepest[scope.value] = best
json.dump({'limit': sys.getrecursionlimit(), 'deepest': deepest}, sys.stdout)
"""


def deepest_resolvable_chain() -> dict[str, int]:
    """Measure the deepest chain a cold `resolve()` survives, by scope.

    The measurement runs in a fresh interpreter, at module level, on the default
    recursion limit. Both are load-bearing: the answer is a frame budget divided by
    `FRAMES_PER_PROVIDER`, so it moves with whatever frames the caller already
    consumed, and a number measured under pytest would pin the test runner's stack
    depth rather than `depin`'s recursion.

    Raises:
        HarnessError: the probe process failed, or printed something other than the
            JSON it is expected to print.
    """
    root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [sys.executable, '-c', CLIFF_PROBE],
        cwd=root,
        env=os.environ | {'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise HarnessError(f'the depth probe exited {completed.returncode}\n{completed.stderr}')
    try:
        measured: object = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError(f'the depth probe printed {completed.stdout!r}, which is not JSON') from error
    if not is_object(measured):
        raise HarnessError(f'the depth probe printed {completed.stdout!r}, which is not a JSON object')
    deepest = require_object(measured.get('deepest'), 'the depth probe')
    return {scope: require_integer(depth, f'the depth probe: {scope}') for scope, depth in deepest.items()}
