"""Enforce the mutation-testing threshold from mutmut's CI statistics."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

MINIMUM_KILLED_PERCENT = 85.0


@dataclass(frozen=True, slots=True)
class MutationStats:
    killed: int
    survived: int
    total: int
    no_tests: int
    skipped: int
    suspicious: int
    timeout: int
    check_was_interrupted_by_user: int
    segfault: int


def _is_json_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _read_stats(path: Path) -> MutationStats | str:
    try:
        contents = path.read_text()
    except OSError as error:
        return f'cannot read mutation stats: {error}'

    try:
        decoded: object = json.loads(contents)
    except json.JSONDecodeError as error:
        return f'invalid JSON: {error.msg}'

    if not _is_json_object(decoded):
        return 'mutation stats must be a JSON object'

    stats = decoded
    required = (
        'killed',
        'survived',
        'total',
        'no_tests',
        'skipped',
        'suspicious',
        'timeout',
        'check_was_interrupted_by_user',
        'segfault',
    )
    values: dict[str, int] = {}
    for field in required:
        value = stats.get(field)
        if field not in stats:
            return f'mutation stats missing field: {field}'
        if isinstance(value, bool) or not isinstance(value, int):
            return f'mutation stats field {field} must be an integer'
        if value < 0:
            return f'mutation stats field {field} must not be negative'
        values[field] = value

    mutation_stats = MutationStats(
        killed=values['killed'],
        survived=values['survived'],
        total=values['total'],
        no_tests=values['no_tests'],
        skipped=values['skipped'],
        suspicious=values['suspicious'],
        timeout=values['timeout'],
        check_was_interrupted_by_user=values['check_was_interrupted_by_user'],
        segfault=values['segfault'],
    )
    counted = sum(
        (
            mutation_stats.killed,
            mutation_stats.survived,
            mutation_stats.no_tests,
            mutation_stats.skipped,
            mutation_stats.suspicious,
            mutation_stats.timeout,
            mutation_stats.check_was_interrupted_by_user,
            mutation_stats.segfault,
        ),
    )
    if mutation_stats.total > counted:
        unclassified = mutation_stats.total - counted
        noun = 'result is' if unclassified == 1 else 'results are'
        return f'{unclassified} mutation {noun} unclassified by mutmut CI statistics'
    if mutation_stats.total < counted:
        return f'mutation stats have inconsistent totals: total={mutation_stats.total}, counted={counted}'
    return mutation_stats


def evaluate(stats: MutationStats) -> str | None:
    inconclusive = (
        ('no_tests', stats.no_tests),
        ('skipped', stats.skipped),
        ('suspicious', stats.suspicious),
        ('check_was_interrupted_by_user', stats.check_was_interrupted_by_user),
        ('segfault', stats.segfault),
    )
    found = [f'{name}={count}' for name, count in inconclusive if count]
    if found:
        return f'mutation run has inconclusive results: {", ".join(found)}'

    decided = stats.killed + stats.timeout + stats.survived
    if decided == 0:
        return 'mutation run decided no mutants'
    killed_percent = (stats.killed + stats.timeout) / decided * 100
    if killed_percent < MINIMUM_KILLED_PERCENT:
        return (
            f'mutation score is {killed_percent:.1f}%, below the {MINIMUM_KILLED_PERCENT:.1f}% threshold; '
            f'survivors must be at most {100 - MINIMUM_KILLED_PERCENT:.1f}% of decided mutants'
        )
    return None


def main(arguments: list[str] | None = None) -> int:
    paths = sys.argv[1:] if arguments is None else arguments
    if len(paths) != 1:
        print('expected exactly one stats JSON path')
        return 1

    result = _read_stats(Path(paths[0]))
    if isinstance(result, str):
        print(result)
        return 1

    error = evaluate(result)
    decided = result.killed + result.timeout + result.survived
    score = (result.killed + result.timeout) / decided * 100 if decided else 0.0
    print(
        f'mutation score: {score:.1f}% '
        f'({result.killed} killed, {result.timeout} timed out, {result.survived} survived, {result.total} total)'
    )
    if error is not None:
        print(error)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
