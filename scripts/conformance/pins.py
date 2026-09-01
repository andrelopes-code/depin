"""`checkers.toml`, the `uv.lock` lockstep check, and the corpus import ban."""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from scripts.conformance.model import (
    CHECKER_NAMES,
    CHECKOUT,
    CONFORMANCE,
    ConformanceError,
    Pins,
    is_array,
    is_table,
    load_toml,
    strings,
    table,
    text,
)

FORBIDDEN_IMPORTS: Final = ('depin._core', 'from depin import _')


def read_pins(path: Path) -> Pins:
    document = load_toml(path)
    targets = table(document.get('targets'), f'{path.name} [targets]')
    checkers = table(document.get('checkers'), f'{path.name} [checkers]')
    install = table(document.get('install'), f'{path.name} [install]')
    lockstep = table(document.get('lockstep'), f'{path.name} [lockstep]')
    modules = table(install.get('framework_modules'), f'{path.name} [install.framework_modules]')
    return Pins(
        versions={name: text(checkers, name, str(path)) for name in CHECKER_NAMES},
        python=text(targets, 'python', str(path)),
        platform=text(targets, 'os', str(path)),
        extras=strings(install.get('extras'), f'{path.name} [install] extras'),
        framework_modules=tuple(text(modules, key, str(path)) for key in sorted(modules)),
        lockstep={name: text(lockstep, name, str(path)) for name in sorted(lockstep)},
    )


def override_pins(pins: Pins, versions: Mapping[str, str], python: str | None) -> Pins:
    """Run the suite against a version or a language target other than the committed one.

    `typing-forward` probes the newest release of each checker weekly, and the
    lockstep assertion has to stand aside for exactly the checkers it
    overrides: `uv.lock` still resolves the committed pin, so comparing a
    deliberately different version against it would fail every forward run.
    Nothing here writes `checkers.toml` — advancing a pin is a pull request
    that shows the whole suite green on the new version.
    """
    if not versions and python is None:
        return pins
    return Pins(
        versions={**pins.versions, **versions},
        python=python if python is not None else pins.python,
        platform=pins.platform,
        extras=pins.extras,
        framework_modules=pins.framework_modules,
        lockstep={name: distribution for name, distribution in pins.lockstep.items() if name not in versions},
    )


def verify_lockstep(pins: Pins) -> None:
    """The pinned mypy and basedpyright must equal what `uv.lock` resolves.

    Comparing against the declared floor would prove nothing: `dev` declares
    ``mypy>=1.18``, which every future resolution satisfies while ``uv run
    mypy`` and ``uvx mypy@2.3.1`` drift apart. Dependabot runs weekly, so the
    drift is scheduled rather than hypothetical.
    """
    lock = load_toml(CHECKOUT / 'uv.lock')
    packages = lock.get('package')
    if not is_array(packages):
        raise ConformanceError('uv.lock carries no package array')
    resolved: dict[str, str] = {}
    for entry in packages:
        if not is_table(entry):
            continue
        name = entry.get('name')
        version = entry.get('version')
        if isinstance(name, str) and isinstance(version, str):
            resolved[name] = version
    for checker, distribution in pins.lockstep.items():
        locked = resolved.get(distribution)
        pinned = pins.versions[checker]
        if locked is None:
            raise ConformanceError(f'uv.lock does not resolve {distribution}, which checkers.toml pins at {pinned}')
        if locked != pinned:
            raise ConformanceError(
                f'{checker}: checkers.toml pins {pinned} but uv.lock resolves {distribution} {locked}; '
                'advance the pin in a pull request that shows the suite green on the new version'
            )


def verify_corpus_imports() -> None:
    """The corpus is consumer code, so it reaches nothing private. The check is textual."""
    offenders: list[str] = []
    for path in sorted(CONFORMANCE.rglob('*.py')):
        contents = path.read_text(encoding='utf-8')
        offenders.extend(
            f'{path.relative_to(CHECKOUT)} contains {needle!r}' for needle in FORBIDDEN_IMPORTS if needle in contents
        )
    if offenders:
        raise ConformanceError('the corpus reaches into private API: ' + '; '.join(offenders))
