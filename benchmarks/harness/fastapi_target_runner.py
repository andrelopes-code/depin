#!/usr/bin/env python3
"""Neutral, copyable target-local FastAPI semantic probe runner.

The runner intentionally imports no repository module until after it has proved
that ``--source-root`` is the requested clean checkout.  Copy this file outside
both target trees and invoke it with an isolated interpreter:

    ENV/bin/python -I fastapi_target_runner.py --source-root TREE \
      --expected-revision SHA --out EXTERNAL/probes/base/rep0.json
"""

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

WORKLOADS = (
    'fastapi_cpu_light_endpoint',
    'fastapi_request_scoped_graph',
    'fastapi_singletons_and_transients',
    'fastapi_async_resource_teardown',
    'fastapi_endpoint_with_work',
    'fastapi_application_startup',
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(('git', '-C', str(root), *arguments), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f'git -C {root} {" ".join(arguments)} failed: {completed.stderr.strip()}')
    return completed.stdout.strip()


def clean_target(root: Path, expected: str) -> None:
    if git(root, 'rev-parse', 'HEAD') != expected:
        raise RuntimeError('target revision differs from --expected-revision')
    if git(root, 'status', '--porcelain'):
        raise RuntimeError('target checkout is dirty')


def under(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError as error:
        raise RuntimeError(f'{resolved} is outside target root {root}') from error


class Observation(Protocol):
    @property
    def result(self) -> object: ...

    @property
    def constructed(self) -> tuple[object, ...]: ...

    @property
    def closed(self) -> tuple[object, ...]: ...


class ObservableImplementation(Protocol):
    def observe(self) -> Observation: ...


def observed(value: Observation) -> dict[str, object]:
    result = value.result
    if not isinstance(result, str):
        raise RuntimeError('workload observation result must be text')
    constructed = value.constructed
    closed = value.closed
    return {'result': result, 'constructed': list(constructed), 'closed': list(closed), 'error': None}


def attempt(implementation: ObservableImplementation) -> dict[str, object]:
    try:
        return observed(implementation.observe())
    except BaseException as error:
        return {'result': None, 'constructed': [], 'closed': [], 'error': f'{type(error).__name__}: {error}'}


def installed(name: str, root: Path) -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f'locked interpreter lacks required distribution {name!r}') from error
    if name == 'pydepin':
        contents = distribution.read_text('direct_url.json')
        if contents is None:
            raise RuntimeError('pydepin must be installed editable from the target checkout')
        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as error:
            raise RuntimeError('pydepin must be installed editable from the target checkout') from error
        url = payload.get('url')
        if not isinstance(url, str) or not url.startswith('file://'):
            raise RuntimeError('pydepin direct_url must bind an editable target checkout')
        from urllib.parse import unquote, urlparse

        if Path(unquote(urlparse(url).path)).resolve() != root.resolve():
            raise RuntimeError('pydepin direct_url is not bound to the target checkout')
        return distribution.version, url
    return distribution.version, ''


def distinct(root: Path, *external: Path) -> None:
    target = root.resolve()
    for path in external:
        candidate = path.resolve()
        if candidate == target or target in candidate.parents or candidate in target.parents:
            raise RuntimeError(f'{candidate} aliases target root {target}')


def capture(
    root: Path,
    expected: str,
    expected_lock: str,
    out: Path,
    bundle: Path,
    environment: Path,
    cache: Path,
    side: str,
    repetition: int,
) -> None:
    distinct(root, out, bundle, environment, cache)
    clean_target(root, expected)
    if digest(root / 'uv.lock') != expected_lock:
        raise RuntimeError('target lock SHA256 differs from --expected-lock-sha256')
    if out.exists():
        raise RuntimeError(f'{out} already exists; raw target records are immutable')
    sys.path.insert(0, str(root))
    from benchmarks.workloads.application.inventory import WORKLOADS as inventory

    selected = {workload.name: workload for workload in inventory}
    if set(WORKLOADS) - set(selected):
        raise RuntimeError('target checkout lacks a required common FastAPI workload')
    imports = {}
    for module in (
        'depin',
        'benchmarks',
        'benchmarks.test_latency',
        'benchmarks.workloads.application.inventory',
    ):
        loaded = __import__(module, fromlist=['__file__'])
        location = getattr(loaded, '__file__', None)
        if not isinstance(location, str):
            raise RuntimeError(f'{module} has no resolved file')
        imports[module] = under(Path(location), root)
    records: list[dict[str, object]] = []
    for name in WORKLOADS:
        workload = selected[name]
        if workload.baseline is None:
            raise RuntimeError(f'{name} lacks a direct implementation')
        records.append(
            {
                'workload': name,
                'depin': attempt(workload.subject),
                'direct': attempt(workload.baseline),
            }
        )
    clean_target(root, expected)
    payload = {
        'schema_version': 2,
        'side': side,
        'repetition': repetition,
        'revision': expected,
        'source_root': str(root.resolve()),
        'interpreter': str(Path(sys.executable).resolve()),
        'prefix': str(Path(sys.prefix).resolve()),
        'lock_sha256': digest(root / 'uv.lock'),
        'runner_sha256': digest(Path(__file__)),
        'clean_before': True,
        'clean_after': True,
        'pins': {
            name: installed(name, root)[0] for name in ('pydepin', 'pytest', 'pytest-benchmark', 'fastapi', 'starlette')
        },
        'pydepin_direct_url': installed('pydepin', root)[1],
        'imports': imports,
        'observations': records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=out.parent, delete=False) as temporary:
        json.dump(payload, temporary, sort_keys=True, separators=(',', ':'))
        temporary.write('\n')
        name = temporary.name
    Path(name).replace(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--expected-revision', required=True)
    parser.add_argument('--expected-lock-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bundle-root', type=Path, required=True)
    parser.add_argument('--environment-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--side', choices=('base', 'head'), required=True)
    parser.add_argument('--repetition', type=int, required=True)
    arguments = parser.parse_args()
    try:
        capture(
            arguments.source_root,
            arguments.expected_revision,
            arguments.expected_lock_sha256,
            arguments.out,
            arguments.bundle_root,
            arguments.environment_root,
            arguments.cache_root,
            arguments.side,
            arguments.repetition,
        )
    except RuntimeError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
