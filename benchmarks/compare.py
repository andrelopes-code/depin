"""Compare two pytest-benchmark JSON reports and fail on a regression.

Run as ``python -m benchmarks.compare base.json head.json --max-regression=0.25``.
Exits 1 when any benchmark present in both reports is slower in the second by
more than the given ratio.
"""

import json
import pathlib
import sys


def _means(report: pathlib.Path) -> dict[str, float]:
    """Map each benchmark's full name to its mean time, in seconds."""
    payload = json.loads(report.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise SystemExit(f'{report}: expected a JSON object at the top level')
    entries = payload.get('benchmarks')
    if not isinstance(entries, list):
        raise SystemExit(f'{report}: no "benchmarks" array')

    means: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get('fullname')
        stats = entry.get('stats')
        if not isinstance(name, str) or not isinstance(stats, dict):
            continue
        mean = stats.get('mean')
        if isinstance(mean, int | float):
            means[name] = float(mean)
    return means


def main(argv: list[str]) -> int:
    # Shared CI runners are noisy; 25% catches an order-of-magnitude
    # regression without failing the build on ordinary run-to-run drift.
    limit = 0.25
    positional: list[str] = []
    for argument in argv:
        if argument.startswith('--max-regression='):
            limit = float(argument.split('=', 1)[1])
        else:
            positional.append(argument)

    if len(positional) != 2:
        print('usage: python -m benchmarks.compare BASE.json HEAD.json [--max-regression=RATIO]', file=sys.stderr)
        return 2

    base = _means(pathlib.Path(positional[0]))
    head = _means(pathlib.Path(positional[1]))

    shared = sorted(set(base) & set(head))
    for name in sorted(set(head) - set(base)):
        print(f'new benchmark, not gated: {name}')

    if not shared:
        print('no benchmark appears in both reports; nothing to compare', file=sys.stderr)
        return 1

    regressions: list[str] = []
    for name in shared:
        before, after = base[name], head[name]
        if before <= 0:
            continue
        ratio = (after - before) / before
        marker = 'REGRESSION' if ratio > limit else 'ok'
        print(f'{marker:<11} {ratio:+7.1%}  {name}')
        if ratio > limit:
            regressions.append(f'{name}: {before:.3e}s -> {after:.3e}s ({ratio:+.1%})')

    if regressions:
        print(f'\n{len(regressions)} benchmark(s) regressed past {limit:.0%}:', file=sys.stderr)
        for line in regressions:
            print(f'  - {line}', file=sys.stderr)
        return 1

    print(f'\n{len(shared)} benchmark(s) within {limit:.0%} of the base branch')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
