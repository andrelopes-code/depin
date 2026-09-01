"""The shared data structures, the error type, and TOML/JSON narrowing."""

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard

CHECKOUT: Final = Path(__file__).resolve().parents[2]
CONFORMANCE: Final = CHECKOUT / 'conformance'
CHECKER_NAMES: Final = ('mypy', 'pyright', 'basedpyright', 'ty', 'pyrefly')
MODES: Final = ('core', 'extras')
STAGES: Final = ('control', 'positive', 'anti-erasure', 'negative', 'divergence')


class ConformanceError(Exception):
    """A precondition of the suite does not hold, so no result it produced would mean anything."""


@dataclass(frozen=True, slots=True)
class Pins:
    versions: Mapping[str, str]
    python: str
    platform: str
    extras: tuple[str, ...]
    framework_modules: tuple[str, ...]
    lockstep: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    corpus: Path
    wheel: Path
    venvs: Mapping[str, Path]


@dataclass(frozen=True, slots=True)
class Invocation:
    config: Path
    venv: Path
    files: tuple[Path, ...]
    anti_erasure: bool


@dataclass(frozen=True, slots=True)
class Diagnostic:
    path: str
    line: int
    rule: str


@dataclass(frozen=True, slots=True)
class Outcome:
    exit_code: int
    diagnostics: tuple[Diagnostic, ...]
    checked: int | None
    output: str


@dataclass(frozen=True, slots=True)
class Checker:
    name: str
    package: str
    config: str
    build: Callable[[str, Invocation], tuple[str, ...]]
    parse: Callable[[int, str, str], Outcome]
    missing_import_rule: str


@dataclass(frozen=True, slots=True)
class Failure:
    checker: str
    mode: str
    stage: str
    detail: str


@dataclass(frozen=True, slots=True)
class Result:
    checker: str
    mode: str
    stage: str
    note: str
    passed: bool


@dataclass(frozen=True, slots=True)
class Selection:
    checkers: tuple[str, ...]
    modes: tuple[str, ...]
    stages: tuple[str, ...]
    wheel: Path | None
    verify_artifact: bool
    source: bool
    overrides: Mapping[str, str]
    target_python: str | None


def is_table(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def is_array(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def table(value: object, where: str) -> dict[str, object]:
    if not is_table(value):
        raise ConformanceError(f'{where} must be a table')
    return value


def text(source: Mapping[str, object], key: str, where: str) -> str:
    value = source.get(key)
    if not isinstance(value, str):
        raise ConformanceError(f'{where}: {key} must be a string')
    return value


def integer(source: Mapping[str, object], key: str, where: str) -> int:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConformanceError(f'{where}: {key} must be an integer')
    return value


def strings(value: object, where: str) -> tuple[str, ...]:
    if not is_array(value):
        raise ConformanceError(f'{where} must be an array of strings')
    items: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ConformanceError(f'{where} must be an array of strings')
        items.append(entry)
    return tuple(items)


def load_toml(path: Path) -> dict[str, object]:
    with path.open('rb') as handle:
        document: object = tomllib.load(handle)
    return table(document, str(path))
