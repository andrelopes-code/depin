"""Deterministic contract for the declarative-discovery performance gate."""

from collections.abc import Callable
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, read_json, require_object, write_json
from benchmarks.harness.discovery_acceptance import (
    DEFAULT_SEED,
    EXIT_FAIL,
    EXIT_INCONCLUSIVE,
    EXIT_INVALID,
    EXIT_PASS,
    Interval,
    Outcome,
    classify_samples,
    main,
    validate_preflight_observations,
    write_result_atomic,
)

_HASH_A = '1' * 64
_HASH_B = '2' * 64
_HASH_C = '3' * 64


def _sample_document(base: list[object], head: list[object], *, resamples: int = 200) -> dict[str, object]:
    pairs = len(base)
    return {
        'schema_version': 1,
        'status': 'complete',
        'protocol': {
            'warmup_pairs': 10,
            'pairs': pairs,
            'minimum_interval_ms': 250,
            'bootstrap_resamples': resamples,
            'seed': DEFAULT_SEED,
            'loops': 100,
        },
        'revisions': {'base': 'a' * 40, 'head': 'b' * 40},
        'hashes': {
            'source': {'base': _HASH_A, 'head': _HASH_B},
            'fixture': _HASH_C,
            'harness': _HASH_A,
            'runtime': {'depin/_core/frozen.py': _HASH_B},
        },
        'environment': {'affinity': [0]},
        'samples': {
            'base_ns': base,
            'head_ns': head,
            'order': ['base-head' if index % 2 == 0 else 'head-base' for index in range(pairs)],
        },
    }


def _write_document(path: Path, base: list[object], head: list[object], *, resamples: int = 200) -> None:
    write_json(path, _sample_document(base, head, resamples=resamples))


def _document_object(document: dict[str, object], key: str) -> dict[str, object]:
    return require_object(document[key], key)


def _make_partial(document: dict[str, object]) -> None:
    document['status'] = 'partial'


def _make_unequal(document: dict[str, object]) -> None:
    _document_object(document, 'samples')['head_ns'] = [1000.0] * 191


def _make_insufficient(document: dict[str, object]) -> None:
    _document_object(document, 'protocol')['pairs'] = 191


def _make_non_finite(document: dict[str, object]) -> None:
    _document_object(document, 'samples')['base_ns'] = [float('nan')] * 192


def _make_malformed(document: dict[str, object]) -> None:
    _document_object(document, 'samples')['base_ns'] = ['slow'] * 192


def test_seeded_bootstrap_has_stable_paired_median_intervals() -> None:
    decision = classify_samples(
        [100.0, 200.0, 400.0],
        [105.0, 220.0, 460.0],
        seed=11,
        bootstrap_resamples=7,
        absolute_limit_ns=100.0,
        relative_limit=2.0,
    )

    assert decision.delta_ns == Interval(point=20.0, low=5.0, high=60.0)
    assert decision.ratio == Interval(point=1.1, low=1.05, high=1.15)
    assert decision.outcome is Outcome.PASS


@pytest.mark.parametrize(
    ('head', 'absolute_limit_ns', 'relative_limit', 'expected'),
    [
        pytest.param([1050.0] * 5, 50.0, 1.05, Outcome.PASS, id='inclusive-pass-boundary'),
        pytest.param([1051.0] * 5, 50.0, 2.0, Outcome.FAIL, id='absolute-fail'),
        pytest.param([1051.0] * 5, 100.0, 1.05, Outcome.FAIL, id='relative-fail'),
        pytest.param([1000.0, 1000.0, 1000.0, 1100.0, 1100.0], 50.0, 2.0, Outcome.INCONCLUSIVE, id='uncertain'),
    ],
)
def test_decision_requires_both_point_and_confidence_bound(
    head: list[float],
    absolute_limit_ns: float,
    relative_limit: float,
    expected: Outcome,
) -> None:
    decision = classify_samples(
        [1000.0] * 5,
        head,
        seed=23,
        bootstrap_resamples=1000,
        absolute_limit_ns=absolute_limit_ns,
        relative_limit=relative_limit,
    )

    assert decision.outcome is expected


@pytest.mark.parametrize(
    ('base', 'head', 'expected'),
    [
        ([1.0], [], 'pairs must match'),
        ([], [], 'no measurements'),
        ([0.0], [1.0], 'finite and positive'),
        ([1.0], [float('nan')], 'finite and positive'),
        ([1.0], [float('inf')], 'finite and positive'),
    ],
)
def test_classifier_rejects_unequal_empty_or_non_finite_samples(
    base: list[float],
    head: list[float],
    expected: str,
) -> None:
    with pytest.raises(HarnessError, match=expected):
        classify_samples(
            base,
            head,
            seed=1,
            bootstrap_resamples=10,
            absolute_limit_ns=50.0,
            relative_limit=1.05,
        )


def test_preflight_rejects_base_or_declarative_observation_mismatch() -> None:
    expected: dict[str, object] = {
        'records': [{'source': 'Leaf'}],
        'specs': [{'key': 'Leaf'}],
        'plan': {'order': ['Leaf']},
    }

    validate_preflight_observations(expected, expected, expected)

    with pytest.raises(HarnessError, match='base manual and head manual'):
        validate_preflight_observations(expected, {'records': []}, expected)
    with pytest.raises(HarnessError, match='head manual and head declarative'):
        validate_preflight_observations(expected, expected, {'plan': {'order': []}})


def test_atomic_result_replaces_the_complete_document(tmp_path: Path) -> None:
    output = tmp_path / 'result.json'
    write_json(output, {'state': 'old'})

    write_result_atomic(output, {'state': 'complete'})

    assert read_json(output) == {'state': 'complete'}
    assert list(tmp_path.iterdir()) == [output]


def test_seed_check_proves_the_known_regression_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            'seed-check',
            '--delta-ns',
            '100',
            '--ratio',
            '1.06',
            '--absolute-limit-ns',
            '50',
            '--relative-limit',
            '1.05',
        ]
    )

    assert exit_code == EXIT_FAIL
    assert '"outcome": "FAIL"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ('flag', 'value'),
    [
        ('--delta-ns', '0'),
        ('--ratio', '1'),
        ('--absolute-limit-ns', '-1'),
        ('--relative-limit', '0'),
    ],
)
def test_seed_check_rejects_invalid_limits_and_regression_values(
    flag: str,
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = {
        '--delta-ns': '100',
        '--ratio': '1.06',
        '--absolute-limit-ns': '50',
        '--relative-limit': '1.05',
    }
    arguments[flag] = value

    exit_code = main(['seed-check', *(item for pair in arguments.items() for item in pair)])

    assert exit_code == EXIT_INVALID
    assert capsys.readouterr().err


@pytest.mark.parametrize(
    ('base', 'head', 'expected_exit', 'expected_outcome'),
    [
        pytest.param([1000.0] * 192, [1050.0] * 192, EXIT_PASS, 'PASS', id='pass'),
        pytest.param([1000.0] * 192, [1060.0] * 192, EXIT_FAIL, 'FAIL', id='fail'),
        pytest.param(
            [1000.0] * 192,
            [1000.0] * 96 + [1100.0] * 96,
            EXIT_INCONCLUSIVE,
            'INCONCLUSIVE',
            id='inconclusive',
        ),
    ],
)
def test_decide_returns_the_verdict_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: list[object],
    head: list[object],
    expected_exit: int,
    expected_outcome: str,
) -> None:
    input_path = tmp_path / 'result.json'
    _write_document(input_path, base, head)

    exit_code = main(
        [
            'decide',
            '--input',
            str(input_path),
            '--absolute-limit-ns',
            '50',
            '--relative-limit',
            '1.05',
        ]
    )

    assert exit_code == expected_exit
    assert f'"outcome": "{expected_outcome}"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ('document_change', 'expected'),
    [
        pytest.param(_make_partial, 'status', id='partial'),
        pytest.param(_make_unequal, 'pairs must match', id='unequal'),
        pytest.param(_make_insufficient, '192 or 384', id='insufficient'),
        pytest.param(_make_non_finite, 'finite and positive', id='non-finite'),
        pytest.param(_make_malformed, 'expected a number', id='malformed'),
    ],
)
def test_decide_rejects_incomplete_or_malformed_sample_documents(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    document_change: Callable[[dict[str, object]], None],
    expected: str,
) -> None:
    input_path = tmp_path / 'result.json'
    document = _sample_document([1000.0] * 192, [1000.0] * 192)
    document_change(document)
    write_json(input_path, document)

    exit_code = main(
        [
            'decide',
            '--input',
            str(input_path),
            '--absolute-limit-ns',
            '50',
            '--relative-limit',
            '1.05',
        ]
    )

    assert exit_code == EXIT_INVALID
    assert expected in capsys.readouterr().err


def test_collect_validates_protocol_before_running_any_measurement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            'collect',
            '--base-dir',
            str(tmp_path),
            '--head-dir',
            str(tmp_path),
            '--fixture-dir',
            str(tmp_path),
            '--warmup-pairs',
            '10',
            '--pairs',
            '0',
            '--minimum-interval-ms',
            '250',
            '--bootstrap-resamples',
            '50000',
            '--seed',
            str(DEFAULT_SEED),
            '--out',
            str(tmp_path / 'result.json'),
        ]
    )

    assert exit_code == EXIT_INVALID
    assert 'pairs' in capsys.readouterr().err
