import json
from pathlib import Path

import pytest

from scripts.check_mutation_threshold import MINIMUM_KILLED_PERCENT, MutationStats, evaluate, main


def mutation_stats(**changes: int) -> MutationStats:
    values = {
        'killed': 85,
        'survived': 15,
        'total': 100,
        'no_tests': 0,
        'skipped': 0,
        'suspicious': 0,
        'timeout': 0,
        'check_was_interrupted_by_user': 0,
        'segfault': 0,
    }
    values.update(changes)
    return MutationStats(**values)


def write_stats(path: Path, values: dict[str, object]) -> None:
    path.write_text(json.dumps(values))


def test_evaluate_accepts_score_at_the_threshold() -> None:
    assert evaluate(mutation_stats()) is None


def test_evaluate_rejects_score_below_threshold() -> None:
    error = evaluate(mutation_stats(killed=84, survived=16))

    assert error is not None
    assert '84.0%' in error
    assert f'{MINIMUM_KILLED_PERCENT:.1f}%' in error
    assert '15.0%' in error


@pytest.mark.parametrize(
    'result',
    ['no_tests', 'skipped', 'suspicious', 'timeout', 'check_was_interrupted_by_user', 'segfault'],
)
def test_evaluate_rejects_inconclusive_results(result: str) -> None:
    assert result in MutationStats.__dataclass_fields__
    assert evaluate(mutation_stats(**{result: 1})) == f'mutation run has inconclusive results: {result}=1'


@pytest.mark.parametrize(
    ('contents', 'expected'),
    [
        ('{', 'invalid JSON'),
        ('[]', 'JSON object'),
        ('{}', 'missing field: killed'),
        ('{"killed": true}', 'must be an integer'),
        ('{"killed": -1}', 'must not be negative'),
        (
            '{"killed": 1, "survived": 1, "total": 1, "no_tests": 0, "skipped": 0, '
            '"suspicious": 0, "timeout": 0, "check_was_interrupted_by_user": 0, "segfault": 0}',
            'inconsistent totals',
        ),
    ],
)
def test_main_rejects_malformed_or_inconsistent_stats(
    tmp_path: Path, contents: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / 'stats.json'
    path.write_text(contents)

    assert main([str(path)]) == 1
    assert expected in capsys.readouterr().out


def test_main_rejects_non_integer_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / 'stats.json'
    values: dict[str, object] = {
        'killed': 95,
        'survived': '5',
        'total': 100,
        'no_tests': 0,
        'skipped': 0,
        'suspicious': 0,
        'timeout': 0,
        'check_was_interrupted_by_user': 0,
        'segfault': 0,
    }
    write_stats(path, values)

    assert main([str(path)]) == 1
    assert 'survived must be an integer' in capsys.readouterr().out


def test_main_rejects_mutants_missing_from_exported_classifications(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / 'stats.json'
    values: dict[str, object] = {
        'killed': 85,
        'survived': 15,
        'total': 101,
        'no_tests': 0,
        'skipped': 0,
        'suspicious': 0,
        'timeout': 0,
        'check_was_interrupted_by_user': 0,
        'segfault': 0,
    }
    write_stats(path, values)

    assert main([str(path)]) == 1
    assert '1 mutation result is unclassified' in capsys.readouterr().out


def test_main_accepts_valid_stats_and_prints_the_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / 'stats.json'
    values: dict[str, object] = {
        'killed': 95,
        'survived': 5,
        'total': 100,
        'no_tests': 0,
        'skipped': 0,
        'suspicious': 0,
        'timeout': 0,
        'check_was_interrupted_by_user': 0,
        'segfault': 0,
    }
    write_stats(path, values)

    assert main([str(path)]) == 0
    assert capsys.readouterr().out == 'mutation score: 95.0% (95 killed, 5 survived, 100 total)\n'


def test_evaluate_rejects_zero_decided_mutants() -> None:
    assert evaluate(mutation_stats(killed=0, survived=0, total=0)) == 'mutation run decided no mutants'


def test_main_requires_exactly_one_stats_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 1
    assert 'expected exactly one stats JSON path' in capsys.readouterr().out
