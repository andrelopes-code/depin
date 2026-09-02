"""Load authored absolute performance targets from TOML."""

import tomllib
from pathlib import Path

from benchmarks.comparison.contracts import AbsoluteTarget
from benchmarks.harness import HarnessError, require_number, require_object, require_text


def load(path: Path) -> dict[str, AbsoluteTarget]:
    """Load and validate the target tables at ``path``.

    Raises:
        HarnessError: the file cannot be read, is malformed TOML, or contains an
            invalid target table.
    """
    try:
        contents = path.read_text(encoding='utf-8')
        decoded = tomllib.loads(contents)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as error:
        raise HarnessError(f'{path}: cannot load targets ({error})') from error

    allowed = {'fixed_seconds', 'fraction_of_direct', 'justification'}
    targets: dict[str, AbsoluteTarget] = {}
    for name, encoded in decoded.items():
        fields = require_object(encoded, name)
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise HarnessError(f'{name}: unknown field {unknown[0]!r}')
        fraction = fields.get('fraction_of_direct')
        targets[name] = AbsoluteTarget(
            fixed_seconds=require_number(fields.get('fixed_seconds'), f'{name}.fixed_seconds'),
            fraction_of_direct=None if fraction is None else require_number(fraction, f'{name}.fraction_of_direct'),
            justification=require_text(fields.get('justification'), f'{name}.justification'),
        )
    return targets
