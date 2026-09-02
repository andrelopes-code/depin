"""The measurement harness: pairing, reduction, statistics, gating and publication.

Nothing here imports `pytest-benchmark`. The plugin writes JSON; this package
reads it. A gate that never imports the tool it reads from stays runnable against
a report captured on another machine, another interpreter, or another version of
the plugin.

The whole package is standard library only, for the same reason `depin` itself is:
a dependency added to the thing that guards the release is a dependency the
release now has.

This module carries what every other one needs — the single error type, and the
narrowing helpers that turn a decoded JSON value into a shape the rest of the code
can rely on without `Any`.
"""

import json
from pathlib import Path
from typing import TypeGuard


class HarnessError(Exception):
    """An input the harness will not proceed on.

    Every failure the harness detects is one of these. Guessing at a malformed
    report is worse than stopping, because the guess is what a regression hides
    behind.
    """


def is_object(value: object) -> TypeGuard[dict[str, object]]:
    """Whether `value` is a decoded JSON object. JSON keys are strings, so the narrowing holds."""
    return isinstance(value, dict)


def is_array(value: object) -> TypeGuard[list[object]]:
    """Whether `value` is a decoded JSON array."""
    return isinstance(value, list)


def read_json(path: Path) -> dict[str, object]:
    """Decode `path` as a JSON object.

    Raises:
        HarnessError: the file cannot be read, does not decode as JSON, or
            decodes to something other than an object.
    """
    try:
        contents = path.read_text(encoding='utf-8')
    except OSError as error:
        raise HarnessError(f'{path}: cannot be read ({error})') from error
    try:
        decoded: object = json.loads(contents)
    except json.JSONDecodeError as error:
        raise HarnessError(f'{path}: is not JSON ({error.msg} at line {error.lineno})') from error
    if not is_object(decoded):
        raise HarnessError(f'{path}: expected a JSON object at the top level, found {type(decoded).__name__}')
    return decoded


def require_object(value: object, where: str) -> dict[str, object]:
    """Narrow `value` to a JSON object, naming `where` it came from when it is not."""
    if not is_object(value):
        raise HarnessError(f'{where}: expected an object, found {type(value).__name__}')
    return value


def require_array(value: object, where: str) -> list[object]:
    """Narrow `value` to a JSON array, naming `where` it came from when it is not."""
    if not is_array(value):
        raise HarnessError(f'{where}: expected an array, found {type(value).__name__}')
    return value


def require_text(value: object, where: str) -> str:
    """Narrow `value` to a non-empty string, naming `where` it came from when it is not."""
    if not isinstance(value, str) or not value:
        raise HarnessError(f'{where}: expected a non-empty string, found {value!r}')
    return value


def require_number(value: object, where: str) -> float:
    """Narrow `value` to a real number.

    `bool` is rejected explicitly: it is an `int` to `isinstance`, and a budget or
    a duration that decoded as `True` is a malformed file rather than the number 1.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise HarnessError(f'{where}: expected a number, found {value!r}')
    return float(value)


def require_integer(value: object, where: str) -> int:
    """Narrow `value` to an integer, rejecting `bool` for the reason `require_number` does."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise HarnessError(f'{where}: expected an integer, found {value!r}')
    return value


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write `payload` to `path` with sorted keys, so two runs of the same data differ nowhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    _ = path.write_text(f'{text}\n', encoding='utf-8')
