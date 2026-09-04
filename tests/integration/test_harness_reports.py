import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from test_harness_gate import flat, make_dataset

from benchmarks.contracts import Tier
from benchmarks.harness import HarnessError, reduce, report, require_object


def _benchmark_report(entries: Sequence[dict[str, object]]) -> dict[str, object]:
    return {'machine_info': {}, 'commit_info': {}, 'benchmarks': list(entries)}


def _entry(name: str, *, mean: float = 1e-6, rounds: int = 5000) -> dict[str, object]:
    return {
        'name': name,
        'fullname': f'benchmarks/test_probe.py::{name}',
        'stats': {'rounds': rounds, 'min': mean, 'median': mean, 'mean': mean, 'stddev': 0.0, 'iqr': 0.0},
    }


def aggregate_of(*, rounds: int, mean: float) -> reduce.Aggregate:
    return reduce.Aggregate(name='probe', rounds=rounds, minimum=mean, median=mean, mean=mean, stddev=0.0, iqr=0.0)


MALFORMED_REPORTS: list[tuple[object, str]] = [
    ([1, 2, 3], 'expected a JSON object'),
    ({'machine_info': {}}, 'expected an array'),
    ({'benchmarks': {}}, 'expected an array'),
    ({'benchmarks': []}, 'is empty'),
    ({'benchmarks': [{'name': 'one'}]}, 'stats'),
    ({'benchmarks': [{'stats': {}}]}, 'name'),
]


def write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_a_report_reduces_to_one_aggregate_per_workload(tmp_path: Path) -> None:
    path = write(tmp_path / 'report.json', _benchmark_report([_entry('one'), _entry('two', mean=2e-6)]))

    reduced = reduce.load(path)

    assert sorted(reduced) == ['one', 'two']
    assert reduced['two'].mean == 2e-6
    assert reduced['two'].measured == pytest.approx(2e-6 * 5000)


@pytest.mark.parametrize(('payload', 'message'), MALFORMED_REPORTS)
def test_a_malformed_report_is_refused(tmp_path: Path, payload: object, message: str) -> None:
    path = write(tmp_path / 'report.json', payload)

    with pytest.raises(HarnessError, match=message):
        _ = reduce.load(path)


def test_an_unreadable_report_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='cannot be read'):
        _ = reduce.load(tmp_path / 'absent.json')


def test_a_report_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / 'report.json'
    _ = path.write_text('{', encoding='utf-8')

    with pytest.raises(HarnessError, match='is not JSON'):
        _ = reduce.load(path)


def test_two_benchmarks_under_one_name_are_refused(tmp_path: Path) -> None:
    path = write(tmp_path / 'report.json', _benchmark_report([_entry('one'), _entry('one')]))

    with pytest.raises(HarnessError, match='two benchmarks named one'):
        _ = reduce.load(path)


@pytest.mark.parametrize(
    ('rounds', 'mean', 'expected'),
    [(1000, 1e-9, True), (999, 1e-9, False), (10, 0.05, True), (10, 0.04, False)],
)
def test_sample_quality_needs_a_thousand_rounds_or_half_a_second(rounds: int, mean: float, expected: bool) -> None:
    aggregate = reduce.Aggregate('probe', rounds, mean, mean, mean, 0.0, 0.0)

    assert reduce.qualifies(aggregate) is expected


def test_the_report_renders_the_same_markdown_from_the_same_data(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6),
        head=flat('probe', 2e-6),
        deterministic={
            'base': {},
            'head': {
                'work': {'probe': 13},
                'allocations': {'probe': {'blocks': 4, 'size': 320, 'peak': 4096}},
                'retained': {'probe': 1024},
                'scaling': {'curve': {'sizes': [10, 20], 'costs': [1e-6, 2e-6]}},
            },
        },
    )

    rendered = report.render(dataset)

    assert rendered == report.render(dataset)
    assert '## Latency' in rendered
    assert '## Work' in rendered
    assert '## Allocations' in rendered
    assert '## Retained memory' in rendered
    assert '## Scaling' in rendered
    assert '2.000 µs' in rendered
    assert str(tmp_path) not in rendered


def test_the_report_refuses_a_dataset_it_cannot_read(tmp_path: Path) -> None:
    assert report.main([str(tmp_path / 'absent')]) == 2


def test_the_tail_quantiles_are_computed_from_the_round_array(tmp_path: Path) -> None:
    """pytest-benchmark reports a median and an interquartile range; a p99 exists only in the data."""
    entry = _entry('probe')
    require_object(entry['stats'], 'stats')['data'] = [float(value) for value in range(1, 101)]

    reduced = reduce.load(write(tmp_path / 'report.json', _benchmark_report([entry])))['probe']

    assert reduced.p95 == pytest.approx(95.05)
    assert reduced.p99 == pytest.approx(99.01)


def test_an_entry_with_no_round_array_carries_no_quantiles(tmp_path: Path) -> None:
    reduced = reduce.load(write(tmp_path / 'report.json', _benchmark_report([_entry('probe')])))['probe']

    assert reduced.p95 is None
    assert reduced.p99 is None


def test_the_cpu_reading_and_the_tier_are_read_from_extra_info(tmp_path: Path) -> None:
    entry = _entry('probe')
    entry['extra_info'] = {'cpu_nanoseconds': 4321, 'tier': Tier.APPLICATION.value}

    reduced = reduce.load(write(tmp_path / 'report.json', _benchmark_report([entry])))['probe']

    assert reduced.cpu == 4321
    assert reduced.tier == Tier.APPLICATION.value


def test_an_aggregate_carrying_no_optional_reading_stores_none_of_them() -> None:
    stored = reduce.encode(aggregate_of(rounds=10, mean=1e-6))

    assert set(stored) == {'rounds', 'minimum', 'median', 'mean', 'stddev', 'iqr'}


def test_every_reading_survives_the_round_trip_the_dataset_is_stored_through() -> None:
    measured = reduce.Aggregate(
        name='probe',
        rounds=10,
        minimum=1e-6,
        median=2e-6,
        mean=3e-6,
        stddev=4e-6,
        iqr=5e-6,
        p95=6e-6,
        p99=7e-6,
        cpu=8.0,
        tier=Tier.APPLICATION.value,
    )

    assert reduce.decode('probe', reduce.encode(measured), 'round trip') == measured
