"""Focused paired acceptance gate for declarative provider discovery."""

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from benchmarks.harness import (
    HarnessError,
    quantile,
    read_json,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_schema_version,
    require_text,
    write_json,
)
from benchmarks.harness import environment as environment_module

SCHEMA_VERSION = 1
DEFAULT_SEED = 2026091102
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INVALID = 2
EXIT_INCONCLUSIVE = 3
LOWER_QUANTILE = 0.025
UPPER_QUANTILE = 0.975
VALID_PAIR_COUNTS = frozenset({192, 384})
RUNTIME_FILES = (
    'depin/_core/providers.py',
    'depin/_core/graph.py',
    'depin/_core/frozen.py',
    'depin/_core/generated.py',
    'depin/_core/instructions.py',
    'depin/_core/construct.py',
    'depin/_core/scope.py',
    'depin/_core/overrides.py',
    'depin/_core/injection.py',
    'depin/_core/teardown.py',
)

FIXTURE_SOURCE = """\
import gc
import json
import os
import statistics
import sys
from time import perf_counter_ns


def pin_cpu():
    requested = os.environ.get('DEPIN_DISCOVERY_CPU')
    if requested is not None and hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, {int(requested)})


class Leaf:
    pass


class Middle:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Root:
    def __init__(self, middle: Middle):
        self.middle = middle


def records_for(construction):
    from depin import Container, Scope

    if construction == 'manual':
        return (
            Container()
            .bind(Leaf, scope=Scope.TRANSIENT)
            .bind(Middle, scope=Scope.TRANSIENT)
            .bind(Root, scope=Scope.TRANSIENT)
            .records()
        )
    if construction == 'declarative':
        from depin import Catalog, Manifest, provider

        catalog = Catalog(
            __name__,
            provider(Leaf).configure(scope=Scope.TRANSIENT),
            provider(Middle).configure(scope=Scope.TRANSIENT),
            provider(Root).configure(scope=Scope.TRANSIENT),
        )
        return Manifest(__name__, catalog).records()
    raise SystemExit(f'unknown construction {construction!r}')


def symbol(value):
    if value is None:
        return None
    if isinstance(value, str):
        return f'str:{value}'
    module = getattr(value, '__module__', type(value).__module__)
    qualname = getattr(value, '__qualname__', type(value).__qualname__)
    return f'{module}.{qualname}'


def normalized_record(record):
    return {
        'source': symbol(record.source),
        'scope': record.scope.value,
        'provides': symbol(record.provides),
        'tag': record.tag,
        'condition': record.condition,
        'check': symbol(record.check),
    }


def normalized_spec(spec):
    return {
        'key': symbol(spec.key),
        'tag': spec.tag,
        'source': symbol(spec.source),
        'scope': spec.scope.value,
        'shape': spec.shape.value,
        'needs_async': spec.needs_async,
        'params': [
            {
                'name': parameter.name,
                'key': symbol(parameter.key),
                'tag': parameter.tag,
                'has_default': parameter.has_default,
                'default': repr(parameter.default) if parameter.has_default else None,
                'optional': parameter.optional,
            }
            for parameter in spec.params
        ],
        'check': symbol(spec.check),
    }


def observe(construction):
    from depin._core.graph import build_plan
    from depin._core.providers import build_specs

    records = tuple(records_for(construction))
    specs = build_specs(records)
    plan = build_plan(records)
    by_key = [
        {'key': symbol(key), 'tag': tag}
        for key, tag in plan.by_key
    ]
    by_key.sort(key=lambda value: json.dumps(value, sort_keys=True))
    return {
        'records': [normalized_record(record) for record in records],
        'specs': [normalized_spec(spec) for spec in specs.providers],
        'plan': {
            'order': [normalized_spec(spec) for spec in plan.order],
            'by_key': by_key,
            'inactive': [],
        },
    }


def measure(construction, loops):
    from depin._core.frozen import FrozenContainer
    from depin._core.graph import build_plan

    frozen = FrozenContainer(build_plan(records_for(construction)))
    frozen.resolve(Root)
    gc.collect()
    started = perf_counter_ns()
    for _ in range(loops):
        frozen.resolve(Root)
    return perf_counter_ns() - started


def calibrate(construction, minimum_ns):
    loops = 1
    while True:
        elapsed = measure(construction, loops)
        if elapsed >= minimum_ns:
            return {'loops': loops, 'elapsed_ns': elapsed}
        loops = max(loops + 1, int(loops * minimum_ns / max(elapsed, 1) * 1.05))


def main():
    pin_cpu()
    operation = sys.argv[1]
    construction = sys.argv[2]
    if operation == 'observe':
        payload = observe(construction)
    elif operation == 'calibrate':
        payload = calibrate(construction, int(sys.argv[3]))
    elif operation == 'measure':
        loops = int(sys.argv[3])
        elapsed = measure(construction, loops)
        payload = {'loops': loops, 'elapsed_ns': elapsed, 'ns_per_operation': elapsed / loops}
    else:
        raise SystemExit(f'unknown operation {operation!r}')
    print(json.dumps(payload, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
"""


class Outcome(StrEnum):
    PASS = 'PASS'
    FAIL = 'FAIL'
    INCONCLUSIVE = 'INCONCLUSIVE'


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: Outcome
    delta_ns: Interval
    ratio: Interval
    absolute_limit_ns: float
    relative_limit: float


@dataclass(frozen=True, slots=True)
class _ValidatedSamples:
    base: tuple[float, ...]
    head: tuple[float, ...]
    seed: int
    bootstrap_resamples: int


@dataclass(frozen=True, slots=True)
class _Side:
    name: str
    directory: Path
    python: Path
    construction: str


def _positive_number(value: object, where: str) -> float:
    number = require_number(value, where)
    if not math.isfinite(number) or number <= 0.0:
        raise HarnessError(f'{where}: expected a finite and positive number, found {value!r}')
    return number


def _non_negative_number(value: object, where: str) -> float:
    number = require_number(value, where)
    if not math.isfinite(number) or number < 0.0:
        raise HarnessError(f'{where}: expected a finite non-negative number, found {value!r}')
    return number


def _positive_integer(value: object, where: str) -> int:
    number = require_integer(value, where)
    if number < 1:
        raise HarnessError(f'{where}: expected a positive integer, found {number}')
    return number


def _positive_samples(values: Sequence[float], side: str) -> None:
    for index, value in enumerate(values):
        if not math.isfinite(value) or value <= 0.0:
            raise HarnessError(f'{side}[{index}] is {value!r}; a duration must be finite and positive')


def _paired_intervals(
    base: Sequence[float], head: Sequence[float], *, seed: int, bootstrap_resamples: int
) -> tuple[Interval, Interval]:
    if len(base) != len(head):
        raise HarnessError(f'{len(base)} base measurements against {len(head)} head measurements; pairs must match')
    if not base:
        raise HarnessError('no measurements to pair')
    if bootstrap_resamples < 1:
        raise HarnessError(f'{bootstrap_resamples} resamples; the bootstrap needs at least one')
    _positive_samples(base, 'base')
    _positive_samples(head, 'head')
    deltas = [after - before for before, after in zip(base, head, strict=True)]
    ratios = [after / before for before, after in zip(base, head, strict=True)]
    generator = random.Random(seed)
    resampled_deltas: list[float] = []
    resampled_ratios: list[float] = []
    for _ in range(bootstrap_resamples):
        indices = [generator.randrange(len(deltas)) for _ in deltas]
        resampled_deltas.append(float(statistics.median(deltas[index] for index in indices)))
        resampled_ratios.append(float(statistics.median(ratios[index] for index in indices)))
    resampled_deltas.sort()
    resampled_ratios.sort()
    return (
        Interval(
            point=float(statistics.median(deltas)),
            low=quantile(resampled_deltas, LOWER_QUANTILE),
            high=quantile(resampled_deltas, UPPER_QUANTILE),
        ),
        Interval(
            point=float(statistics.median(ratios)),
            low=quantile(resampled_ratios, LOWER_QUANTILE),
            high=quantile(resampled_ratios, UPPER_QUANTILE),
        ),
    )


def classify_samples(
    base: Sequence[float],
    head: Sequence[float],
    *,
    seed: int,
    bootstrap_resamples: int,
    absolute_limit_ns: float,
    relative_limit: float,
) -> Decision:
    """Classify paired samples under both transferred acceptance limits."""
    absolute_limit = _non_negative_number(absolute_limit_ns, 'absolute limit')
    relative = _positive_number(relative_limit, 'relative limit')
    delta, ratio = _paired_intervals(base, head, seed=seed, bootstrap_resamples=bootstrap_resamples)
    if (
        delta.point <= absolute_limit
        and delta.high <= absolute_limit
        and ratio.point <= relative
        and ratio.high <= relative
    ):
        outcome = Outcome.PASS
    elif (delta.point > absolute_limit and delta.low > absolute_limit) or (
        ratio.point > relative and ratio.low > relative
    ):
        outcome = Outcome.FAIL
    else:
        outcome = Outcome.INCONCLUSIVE
    return Decision(outcome, delta, ratio, absolute_limit, relative)


def validate_preflight_observations(
    base_manual: Mapping[str, object],
    head_manual: Mapping[str, object],
    head_declarative: Mapping[str, object],
) -> None:
    """Require manual cross-revision and manual/declarative structural equivalence."""
    if base_manual != head_manual:
        raise HarnessError('preflight mismatch between base manual and head manual observations')
    if head_manual != head_declarative:
        raise HarnessError('preflight mismatch between head manual and head declarative observations')


def write_result_atomic(path: Path, payload: dict[str, object]) -> None:
    """Replace a JSON result only after its complete payload is on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        write_json(temporary, payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as error:
        raise HarnessError(f'{path}: cannot be hashed ({error})') from error


def _source_hash(directory: Path) -> str:
    source = directory / 'depin'
    paths = sorted(source.rglob('*.py'))
    if not paths:
        raise HarnessError(f'{source}: no Python package sources found')
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(directory).as_posix().encode()
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        contents = path.read_bytes()
        digest.update(len(contents).to_bytes(8, 'big'))
        digest.update(contents)
    return digest.hexdigest()


def _runtime_hashes(base: Path, head: Path) -> dict[str, object]:
    hashes: dict[str, object] = {}
    for relative in RUNTIME_FILES:
        base_hash = _sha256_file(base / relative)
        head_hash = _sha256_file(head / relative)
        if base_hash != head_hash:
            raise HarnessError(f'preflight runtime mismatch for {relative}: base {base_hash}, head {head_hash}')
        hashes[relative] = base_hash
    return hashes


def _git_revision(directory: Path) -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), cwd=directory, capture_output=True, text=True, check=False)
    revision = completed.stdout.strip()
    if (
        completed.returncode != 0
        or len(revision) != 40
        or any(character not in '0123456789abcdef' for character in revision)
    ):
        raise HarnessError(f'{directory}: cannot determine a lowercase Git HEAD ({completed.stderr.strip()})')
    return revision


def _run_checked(argv: Sequence[str], *, cwd: Path, operation: str) -> None:
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError(
            f'{operation} exited {completed.returncode}: {" ".join(argv)}\n{completed.stdout}{completed.stderr}'
        )


def _venv_python(directory: Path) -> Path:
    relative = Path('Scripts/python.exe') if os.name == 'nt' else Path('bin/python')
    return directory / relative


def _build_environment(name: str, source: Path, fixture_dir: Path) -> Path:
    wheels = fixture_dir / 'wheels' / name
    environment = fixture_dir / 'venvs' / name
    shutil.rmtree(wheels, ignore_errors=True)
    shutil.rmtree(environment, ignore_errors=True)
    wheels.mkdir(parents=True, exist_ok=True)
    _run_checked(('uv', 'build', '--wheel', '--out-dir', str(wheels)), cwd=source, operation=f'{name} wheel build')
    built = sorted(wheels.glob('*.whl'))
    if len(built) != 1:
        raise HarnessError(f'{name}: expected one built wheel in {wheels}, found {len(built)}')
    _run_checked(
        ('uv', 'venv', '--python', sys.executable, str(environment)),
        cwd=fixture_dir,
        operation=f'{name} environment creation',
    )
    python = _venv_python(environment)
    _run_checked(
        ('uv', 'pip', 'install', '--python', str(python), str(built[0])),
        cwd=fixture_dir,
        operation=f'{name} wheel installation',
    )
    return python


def _lowest_affinity_cpu() -> int | None:
    if not hasattr(os, 'sched_getaffinity'):
        return None
    available = os.sched_getaffinity(0)
    return min(available) if available else None


def _run_json(python: Path, runner: Path, arguments: Sequence[str], *, cpu: int | None) -> dict[str, object]:
    child = dict(os.environ)
    child.pop('PYTHONPATH', None)
    child['PYTHONHASHSEED'] = '0'
    if cpu is not None:
        child['DEPIN_DISCOVERY_CPU'] = str(cpu)
    completed = subprocess.run(
        (str(python), str(runner), *arguments),
        cwd=runner.parent,
        env=child,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        output = f'{completed.stdout}{completed.stderr}'
        raise HarnessError(f'{python}: fixture {" ".join(arguments)} exited {completed.returncode}\n{output}')
    try:
        decoded: object = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError(f'{python}: fixture returned malformed JSON ({error.msg})') from error
    return require_object(decoded, f'{python}: fixture output')


def _preflight(base_dir: Path, head_dir: Path, fixture_dir: Path) -> dict[str, object]:
    base = base_dir.resolve()
    head = head_dir.resolve()
    if not base.is_dir() or not head.is_dir():
        raise HarnessError('preflight requires existing --base-dir and --head-dir directories')
    fixture_dir.mkdir(parents=True, exist_ok=True)
    runner = fixture_dir / 'discovery_fixture.py'
    _ = runner.write_text(FIXTURE_SOURCE, encoding='utf-8')
    base_python = _build_environment('base', base, fixture_dir)
    head_python = _build_environment('head', head, fixture_dir)
    cpu = _lowest_affinity_cpu()
    base_manual = _run_json(base_python, runner, ('observe', 'manual'), cpu=cpu)
    head_manual = _run_json(head_python, runner, ('observe', 'manual'), cpu=cpu)
    head_declarative = _run_json(head_python, runner, ('observe', 'declarative'), cpu=cpu)
    validate_preflight_observations(base_manual, head_manual, head_declarative)
    hashes: dict[str, object] = {
        'source': {'base': _source_hash(base), 'head': _source_hash(head)},
        'fixture': _sha256_file(runner),
        'harness': _sha256_file(Path(__file__)),
        'runtime': _runtime_hashes(base, head),
    }
    payload: dict[str, object] = {
        'schema_version': SCHEMA_VERSION,
        'status': 'complete',
        'directories': {'base': str(base), 'head': str(head)},
        'revisions': {'base': _git_revision(base), 'head': _git_revision(head)},
        'interpreters': {'base': str(base_python), 'head': str(head_python)},
        'hashes': hashes,
        'observations': {
            'base_manual': base_manual,
            'head_manual': head_manual,
            'head_declarative': head_declarative,
        },
    }
    write_result_atomic(fixture_dir / 'preflight.json', payload)
    return payload


def _require_hash(value: object, where: str) -> str:
    digest = require_text(value, where)
    if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest):
        raise HarnessError(f'{where}: expected a lowercase SHA-256 digest, found {digest!r}')
    return digest


def _validate_hashes(value: object, where: str) -> dict[str, object]:
    hashes = require_object(value, where)
    source = require_object(hashes.get('source'), f'{where}.source')
    _ = _require_hash(source.get('base'), f'{where}.source.base')
    _ = _require_hash(source.get('head'), f'{where}.source.head')
    _ = _require_hash(hashes.get('fixture'), f'{where}.fixture')
    _ = _require_hash(hashes.get('harness'), f'{where}.harness')
    runtime = require_object(hashes.get('runtime'), f'{where}.runtime')
    if not runtime:
        raise HarnessError(f'{where}.runtime: expected at least one structural hash')
    for name, digest in runtime.items():
        _ = _require_hash(digest, f'{where}.runtime.{name}')
    return hashes


def _preflight_binding(preflight: dict[str, object], base: Path, head: Path, fixture_dir: Path) -> dict[str, object]:
    require_schema_version(preflight, 'preflight', SCHEMA_VERSION)
    if preflight.get('status') != 'complete':
        raise HarnessError('preflight.status: expected complete')
    directories = require_object(preflight.get('directories'), 'preflight.directories')
    if require_text(directories.get('base'), 'preflight.directories.base') != str(base.resolve()):
        raise HarnessError('preflight base directory does not match --base-dir')
    if require_text(directories.get('head'), 'preflight.directories.head') != str(head.resolve()):
        raise HarnessError('preflight head directory does not match --head-dir')
    revisions = require_object(preflight.get('revisions'), 'preflight.revisions')
    if require_text(revisions.get('base'), 'preflight.revisions.base') != _git_revision(base):
        raise HarnessError('preflight base revision changed; run preflight again')
    if require_text(revisions.get('head'), 'preflight.revisions.head') != _git_revision(head):
        raise HarnessError('preflight head revision changed; run preflight again')
    hashes = _validate_hashes(preflight.get('hashes'), 'preflight.hashes')
    source = require_object(hashes.get('source'), 'preflight.hashes.source')
    if source.get('base') != _source_hash(base) or source.get('head') != _source_hash(head):
        raise HarnessError('preflight source hash changed; run preflight again')
    runner = fixture_dir / 'discovery_fixture.py'
    if hashes.get('fixture') != _sha256_file(runner) or hashes.get('harness') != _sha256_file(Path(__file__)):
        raise HarnessError('preflight fixture or harness hash changed; run preflight again')
    if hashes.get('runtime') != _runtime_hashes(base, head):
        raise HarnessError('preflight runtime hashes changed; run preflight again')
    return preflight


def _calibrate(side: _Side, runner: Path, minimum_interval_ms: int, cpu: int | None) -> tuple[int, int]:
    result = _run_json(
        side.python,
        runner,
        ('calibrate', side.construction, str(minimum_interval_ms * 1_000_000)),
        cpu=cpu,
    )
    loops = _positive_integer(result.get('loops'), f'{side.name} calibration.loops')
    elapsed = _positive_integer(result.get('elapsed_ns'), f'{side.name} calibration.elapsed_ns')
    return loops, elapsed


def _measure(side: _Side, runner: Path, loops: int, cpu: int | None) -> float:
    result = _run_json(side.python, runner, ('measure', side.construction, str(loops)), cpu=cpu)
    if _positive_integer(result.get('loops'), f'{side.name} sample.loops') != loops:
        raise HarnessError(f'{side.name}: fixture measured a different loop count')
    return _positive_number(result.get('ns_per_operation'), f'{side.name} sample.ns_per_operation')


def _validate_protocol(
    *, warmup_pairs: int, pairs: int, minimum_interval_ms: int, bootstrap_resamples: int, seed: int
) -> None:
    if warmup_pairs != 10:
        raise HarnessError(f'warmup pairs must be 10, found {warmup_pairs}')
    if pairs not in VALID_PAIR_COUNTS:
        raise HarnessError(f'pairs must be 192 or 384, found {pairs}')
    if minimum_interval_ms < 250:
        raise HarnessError(f'minimum interval must be at least 250 ms, found {minimum_interval_ms}')
    _ = _positive_integer(bootstrap_resamples, 'bootstrap resamples')
    if seed != DEFAULT_SEED:
        raise HarnessError(f'seed must be {DEFAULT_SEED}, found {seed}')


def _collect(
    base_dir: Path,
    head_dir: Path,
    fixture_dir: Path,
    out: Path,
    *,
    warmup_pairs: int,
    pairs: int,
    minimum_interval_ms: int,
    bootstrap_resamples: int,
    seed: int,
) -> dict[str, object]:
    _validate_protocol(
        warmup_pairs=warmup_pairs,
        pairs=pairs,
        minimum_interval_ms=minimum_interval_ms,
        bootstrap_resamples=bootstrap_resamples,
        seed=seed,
    )
    preflight = _preflight_binding(read_json(fixture_dir / 'preflight.json'), base_dir, head_dir, fixture_dir)
    runner = fixture_dir / 'discovery_fixture.py'
    base = _Side('base', base_dir, _venv_python(fixture_dir / 'venvs' / 'base'), 'manual')
    head = _Side('head', head_dir, _venv_python(fixture_dir / 'venvs' / 'head'), 'declarative')
    for side in (base, head):
        if not side.python.is_file():
            raise HarnessError(f'{side.name}: preflight interpreter {side.python} is missing')
    cpu = _lowest_affinity_cpu()
    base_loops, base_calibration_ns = _calibrate(base, runner, minimum_interval_ms, cpu)
    head_loops, head_calibration_ns = _calibrate(head, runner, minimum_interval_ms, cpu)
    loops = max(base_loops, head_loops)
    for index in range(warmup_pairs):
        order = (base, head) if index % 2 == 0 else (head, base)
        for side in order:
            _ = _measure(side, runner, loops, cpu)
    base_samples: list[object] = []
    head_samples: list[object] = []
    orders: list[object] = []
    for index in range(pairs):
        order = (base, head) if index % 2 == 0 else (head, base)
        measured: dict[str, float] = {}
        for side in order:
            measured[side.name] = _measure(side, runner, loops, cpu)
        base_samples.append(measured['base'])
        head_samples.append(measured['head'])
        orders.append(f'{order[0].name}-{order[1].name}')
    captured = environment_module.capture()
    captured['affinity'] = [] if cpu is None else [cpu]
    payload: dict[str, object] = {
        'schema_version': SCHEMA_VERSION,
        'status': 'complete',
        'protocol': {
            'warmup_pairs': warmup_pairs,
            'pairs': pairs,
            'minimum_interval_ms': minimum_interval_ms,
            'bootstrap_resamples': bootstrap_resamples,
            'seed': seed,
            'loops': loops,
        },
        'calibration': {
            'base': {'loops': base_loops, 'elapsed_ns': base_calibration_ns},
            'head': {'loops': head_loops, 'elapsed_ns': head_calibration_ns},
        },
        'revisions': preflight['revisions'],
        'hashes': preflight['hashes'],
        'environment': captured,
        'samples': {'base_ns': base_samples, 'head_ns': head_samples, 'order': orders},
    }
    write_result_atomic(out, payload)
    return payload


def _sample_array(value: object, where: str) -> tuple[float, ...]:
    values = require_array(value, where)
    return tuple(_positive_number(item, f'{where}[{index}]') for index, item in enumerate(values))


def _validated_samples(payload: dict[str, object], path: Path) -> _ValidatedSamples:
    require_schema_version(payload, str(path), SCHEMA_VERSION)
    if payload.get('status') != 'complete':
        raise HarnessError(f'{path}: status must be complete')
    protocol = require_object(payload.get('protocol'), f'{path}: protocol')
    warmup_pairs = require_integer(protocol.get('warmup_pairs'), f'{path}: protocol.warmup_pairs')
    pairs = require_integer(protocol.get('pairs'), f'{path}: protocol.pairs')
    minimum_interval_ms = require_integer(protocol.get('minimum_interval_ms'), f'{path}: protocol.minimum_interval_ms')
    bootstrap_resamples = require_integer(protocol.get('bootstrap_resamples'), f'{path}: protocol.bootstrap_resamples')
    seed = require_integer(protocol.get('seed'), f'{path}: protocol.seed')
    _validate_protocol(
        warmup_pairs=warmup_pairs,
        pairs=pairs,
        minimum_interval_ms=minimum_interval_ms,
        bootstrap_resamples=bootstrap_resamples,
        seed=seed,
    )
    _ = _positive_integer(protocol.get('loops'), f'{path}: protocol.loops')
    revisions = require_object(payload.get('revisions'), f'{path}: revisions')
    for side in ('base', 'head'):
        revision = require_text(revisions.get(side), f'{path}: revisions.{side}')
        if len(revision) != 40 or any(character not in '0123456789abcdef' for character in revision):
            raise HarnessError(f'{path}: revisions.{side} must be a lowercase Git SHA')
    _ = _validate_hashes(payload.get('hashes'), f'{path}: hashes')
    _ = require_object(payload.get('environment'), f'{path}: environment')
    samples = require_object(payload.get('samples'), f'{path}: samples')
    base = _sample_array(samples.get('base_ns'), f'{path}: samples.base_ns')
    head = _sample_array(samples.get('head_ns'), f'{path}: samples.head_ns')
    if len(base) != len(head):
        raise HarnessError(
            f'{path}: {len(base)} base measurements against {len(head)} head measurements; pairs must match'
        )
    if len(base) != pairs:
        raise HarnessError(f'{path}: protocol declares {pairs} pairs but samples contain {len(base)}')
    orders = require_array(samples.get('order'), f'{path}: samples.order')
    if len(orders) != pairs:
        raise HarnessError(f'{path}: expected {pairs} pair-order records, found {len(orders)}')
    for index, order in enumerate(orders):
        expected = 'base-head' if index % 2 == 0 else 'head-base'
        if order != expected:
            raise HarnessError(f'{path}: samples.order[{index}] must be {expected!r}, found {order!r}')
    return _ValidatedSamples(base, head, seed, bootstrap_resamples)


def _decision_payload(decision: Decision) -> dict[str, object]:
    return {
        'outcome': decision.outcome.value,
        'limits': {
            'absolute_ns': decision.absolute_limit_ns,
            'relative': decision.relative_limit,
        },
        'delta_ns': {
            'point': decision.delta_ns.point,
            'l95': decision.delta_ns.low,
            'u95': decision.delta_ns.high,
        },
        'ratio': {
            'point': decision.ratio.point,
            'l95': decision.ratio.low,
            'u95': decision.ratio.high,
        },
    }


def _print_json(payload: dict[str, object]) -> None:
    _ = sys.stdout.write(f'{json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)}\n')


def _outcome_exit(outcome: Outcome) -> int:
    if outcome is Outcome.PASS:
        return EXIT_PASS
    if outcome is Outcome.FAIL:
        return EXIT_FAIL
    return EXIT_INCONCLUSIVE


def _argument(namespace: argparse.Namespace, name: str) -> object:
    return getattr(namespace, name)


def _path_argument(namespace: argparse.Namespace, name: str) -> Path:
    return Path(require_text(_argument(namespace, name), f'--{name.replace("_", "-")}'))


def _integer_argument(namespace: argparse.Namespace, name: str) -> int:
    return require_integer(_argument(namespace, name), f'--{name.replace("_", "-")}')


def _number_argument(namespace: argparse.Namespace, name: str) -> float:
    return require_number(_argument(namespace, name), f'--{name.replace("_", "-")}')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.discovery_acceptance', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)

    seed_check = commands.add_parser('seed-check', help='prove a known regression is rejected')
    seed_check.add_argument('--delta-ns', type=float, required=True)
    seed_check.add_argument('--ratio', type=float, required=True)
    seed_check.add_argument('--absolute-limit-ns', type=float, required=True)
    seed_check.add_argument('--relative-limit', type=float, required=True)

    preflight = commands.add_parser('preflight', help='build isolated environments and prove graph equivalence')
    preflight.add_argument('--base-dir', required=True)
    preflight.add_argument('--head-dir', required=True)
    preflight.add_argument('--fixture-dir', required=True)

    collect = commands.add_parser('collect', help='collect fixed AB/BA paired samples')
    collect.add_argument('--base-dir', required=True)
    collect.add_argument('--head-dir', required=True)
    collect.add_argument('--fixture-dir', required=True)
    collect.add_argument('--warmup-pairs', type=int, required=True)
    collect.add_argument('--pairs', type=int, required=True)
    collect.add_argument('--minimum-interval-ms', type=int, required=True)
    collect.add_argument('--bootstrap-resamples', type=int, required=True)
    collect.add_argument('--seed', type=int, required=True)
    collect.add_argument('--out', required=True)

    decide = commands.add_parser('decide', help='validate samples and apply both transferred limits')
    decide.add_argument('--input', required=True)
    decide.add_argument('--absolute-limit-ns', type=float, required=True)
    decide.add_argument('--relative-limit', type=float, required=True)
    return parser


def _seed_check(namespace: argparse.Namespace) -> int:
    delta = _positive_number(_number_argument(namespace, 'delta_ns'), '--delta-ns')
    ratio = _positive_number(_number_argument(namespace, 'ratio'), '--ratio')
    if ratio <= 1.0:
        raise HarnessError(f'--ratio must be above 1 for the seeded regression, found {ratio}')
    absolute_limit = _non_negative_number(_number_argument(namespace, 'absolute_limit_ns'), '--absolute-limit-ns')
    relative_limit = _positive_number(_number_argument(namespace, 'relative_limit'), '--relative-limit')
    base_value = delta / (ratio - 1.0)
    decision = classify_samples(
        [base_value] * 9,
        [base_value + delta] * 9,
        seed=DEFAULT_SEED,
        bootstrap_resamples=100,
        absolute_limit_ns=absolute_limit,
        relative_limit=relative_limit,
    )
    if decision.outcome is not Outcome.FAIL:
        raise HarnessError(f'seeded regression classified {decision.outcome.value}, expected FAIL')
    _print_json(_decision_payload(decision))
    return EXIT_FAIL


def main(argv: Sequence[str] | None = None) -> int:
    try:
        namespace = _parser().parse_args(argv)
        command = require_text(_argument(namespace, 'command'), 'command')
        if command == 'seed-check':
            return _seed_check(namespace)
        if command == 'preflight':
            payload = _preflight(
                _path_argument(namespace, 'base_dir'),
                _path_argument(namespace, 'head_dir'),
                _path_argument(namespace, 'fixture_dir'),
            )
            _print_json({'status': 'PASS', 'revisions': payload['revisions'], 'hashes': payload['hashes']})
            return EXIT_PASS
        if command == 'collect':
            output = _path_argument(namespace, 'out')
            payload = _collect(
                _path_argument(namespace, 'base_dir'),
                _path_argument(namespace, 'head_dir'),
                _path_argument(namespace, 'fixture_dir'),
                output,
                warmup_pairs=_integer_argument(namespace, 'warmup_pairs'),
                pairs=_integer_argument(namespace, 'pairs'),
                minimum_interval_ms=_integer_argument(namespace, 'minimum_interval_ms'),
                bootstrap_resamples=_integer_argument(namespace, 'bootstrap_resamples'),
                seed=_integer_argument(namespace, 'seed'),
            )
            protocol = require_object(payload.get('protocol'), 'collected protocol')
            _print_json({'status': 'complete', 'out': str(output), 'pairs': protocol['pairs']})
            return EXIT_PASS
        if command == 'decide':
            input_path = _path_argument(namespace, 'input')
            samples = _validated_samples(read_json(input_path), input_path)
            decision = classify_samples(
                samples.base,
                samples.head,
                seed=samples.seed,
                bootstrap_resamples=samples.bootstrap_resamples,
                absolute_limit_ns=_number_argument(namespace, 'absolute_limit_ns'),
                relative_limit=_number_argument(namespace, 'relative_limit'),
            )
            _print_json(_decision_payload(decision))
            return _outcome_exit(decision.outcome)
        raise HarnessError(f'unknown command {command!r}')
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return EXIT_INVALID


if __name__ == '__main__':
    raise SystemExit(main())
