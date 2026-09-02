import json
from pathlib import Path

import pytest

import benchmarks.harness.comparison as comparison
from benchmarks.harness import HarnessError

EXPECTED_IDS = {'resolve-depin', 'resolve-wireup-2.12.0'}


def _child(path: Path) -> Path:
    script = path / 'write_report.py'
    script.write_text(
        """import json
import os
import sys

report = sys.argv[1]
order = os.environ['DEPIN_COMPARISON_ORDER']
mutation = os.environ.get('REPORT_MUTATION')
benchmarks = [
    {'name': 'test_comparison[resolve-depin]', 'stats': {
        'rounds': 1000, 'min': 1.0, 'median': 2.0, 'mean': 2.5, 'stddev': 0.3, 'iqr': 0.4,
        'data': [1.0, 2.0, 3.0, 4.0],
    }, 'extra_info': {'cpu_nanoseconds': 7.0, 'tier': 'component'}},
    {'name': 'test_comparison[resolve-wireup-2.12.0]', 'stats': {
        'rounds': 1000, 'min': 3.0, 'median': 4.0, 'mean': 4.5, 'stddev': 0.6, 'iqr': 0.8,
        'data': [3.0, 4.0, 5.0, 6.0],
    }, 'extra_info': {'cpu_nanoseconds': 11.0, 'tier': 'application'}},
]
if mutation == 'missing':
    benchmarks.pop()
elif mutation == 'extra':
    benchmarks.append({'name': 'test_comparison[unexpected]', 'stats': benchmarks[0]['stats']})
elif mutation == 'fractional_rounds':
    benchmarks[0]['stats']['rounds'] = 1.5
elif mutation == 'negative_minimum':
    benchmarks[0]['stats']['min'] = -1.0
elif mutation == 'nan_median':
    benchmarks[0]['stats']['median'] = float('nan')
elif mutation == 'infinite_mean':
    benchmarks[0]['stats']['mean'] = float('inf')
with open(report, 'w', encoding='utf-8') as stream:
    json.dump({'benchmarks': benchmarks}, stream)
with open(os.environ['CALL_LOG'], 'a', encoding='utf-8') as stream:
    stream.write(order + '\\n')
""",
        encoding='utf-8',
    )
    return script


def test_collection_counterbalances_children_and_reduces_their_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child(tmp_path)
    calls = tmp_path / 'calls.txt'
    monkeypatch.setenv('CALL_LOG', str(calls))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, '_environment', lambda: {'host': 'synthetic'})
    monkeypatch.setattr(comparison, '_descriptions', lambda: {'resolve': {'target': {'seconds': 0.1}}})

    dataset = comparison.collect(
        repetitions=5,
        out=tmp_path / 'out',
        command=(str(child), '{report}'),
    )

    assert calls.read_text(encoding='utf-8').splitlines() == ['forward', 'reverse', 'forward', 'reverse', 'forward']
    assert dataset == {
        'accepted': True,
        'environment': {'host': 'synthetic', 'python_hash_seed': '0'},
        'harness_revision': 'source-revision',
        'pins': {'pydepin': '0.17.1', 'wireup': '2.12.0'},
        'repetitions': [
            {
                'duration': 7000.0,
                'medians': {'test_comparison[resolve-depin]': 2.0, 'test_comparison[resolve-wireup-2.12.0]': 4.0},
                'order': order,
                'rounds': {'test_comparison[resolve-depin]': 1000, 'test_comparison[resolve-wireup-2.12.0]': 1000},
                'samples': {
                    'test_comparison[resolve-depin]': {
                        'cpu': 7.0,
                        'iqr': 0.4,
                        'mean': 2.5,
                        'median': 2.0,
                        'minimum': 1.0,
                        'p95': 3.8499999999999996,
                        'p99': 3.9699999999999998,
                        'rounds': 1000,
                        'stddev': 0.3,
                        'tier': 'component',
                    },
                    'test_comparison[resolve-wireup-2.12.0]': {
                        'cpu': 11.0,
                        'iqr': 0.8,
                        'mean': 4.5,
                        'median': 4.0,
                        'minimum': 3.0,
                        'p95': 5.85,
                        'p99': 5.97,
                        'rounds': 1000,
                        'stddev': 0.6,
                        'tier': 'application',
                    },
                },
            }
            for order in ('forward', 'reverse', 'forward', 'reverse', 'forward')
        ],
        'source_revision': 'source-revision',
        'targets': {'resolve': {'target': {'seconds': 0.1}}},
    }
    assert json.loads((tmp_path / 'out' / 'comparison.json').read_text(encoding='utf-8')) == dataset
    assert not list(tmp_path.rglob('report.json'))


@pytest.mark.parametrize(
    ('clean', 'pins', 'message'),
    [
        (False, {'pydepin': '0.17.1'}, 'dirty'),
        (True, {'pydepin': 'wrong'}, 'pydepin'),
    ],
)
def test_preflight_refuses_dirty_trees_and_pin_mismatches_before_spawning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean: bool,
    pins: dict[str, str],
    message: str,
) -> None:
    monkeypatch.setattr(comparison, '_clean_tree', lambda: clean)
    monkeypatch.setattr(comparison, '_pins', lambda: pins)
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})

    with pytest.raises(HarnessError, match=message):
        _ = comparison.collect(repetitions=5, out=tmp_path / 'out', command=('-c', 'raise SystemExit(3)'))

    assert not (tmp_path / 'out').exists()


def test_collection_requires_at_least_five_repetitions(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='at least five'):
        _ = comparison.collect(repetitions=4, out=tmp_path)


def test_dirty_collection_is_diagnostic_evidence_when_explicitly_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child(tmp_path)
    monkeypatch.setenv('CALL_LOG', str(tmp_path / 'calls.txt'))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: False)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, '_environment', lambda: {'host': 'synthetic'})
    monkeypatch.setattr(comparison, '_descriptions', lambda: dict[str, object]())

    dataset = comparison.collect(
        repetitions=5, out=tmp_path / 'out', allow_dirty=True, command=(str(child), '{report}')
    )

    assert dataset['accepted'] is False


def test_failed_children_leave_no_round_report_in_the_controlled_scratch_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = tmp_path / 'fail.py'
    child.write_text(
        """from pathlib import Path
import sys

Path(sys.argv[1]).write_text('{}', encoding='utf-8')
raise SystemExit(23)
""",
        encoding='utf-8',
    )
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='exited 23'):
        _ = comparison.collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))

    assert not list(tmp_path.rglob('report.json'))


@pytest.mark.parametrize(
    ('mutation', 'message'),
    [
        ('missing', 'missing'),
        ('extra', 'unexpected'),
        ('fractional_rounds', 'rounds'),
        ('negative_minimum', 'stats.min'),
        ('nan_median', 'median'),
        ('infinite_mean', 'mean'),
    ],
)
def test_collection_refuses_malformed_or_incomplete_raw_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, message: str
) -> None:
    child = _child(tmp_path)
    monkeypatch.setenv('CALL_LOG', str(tmp_path / 'calls.txt'))
    monkeypatch.setenv('REPORT_MUTATION', mutation)
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match=message):
        _ = comparison.collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))


def test_collection_times_out_a_blocked_child_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    child = tmp_path / 'blocked.py'
    child.write_text('import signal\nsignal.pause()\n', encoding='utf-8')
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='timed out'):
        _ = comparison.collect(
            repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'), timeout_seconds=0.01
        )

    assert not list(tmp_path.rglob('report.json'))


@pytest.mark.parametrize('failure', ['write', 'replace'])
def test_atomic_collection_preserves_existing_evidence_when_finalization_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    child = _child(tmp_path)
    destination = tmp_path / 'out' / 'comparison.json'
    destination.parent.mkdir()
    destination.write_text('{"existing": true}\n', encoding='utf-8')
    monkeypatch.setenv('CALL_LOG', str(tmp_path / 'calls.txt'))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
    if failure == 'write':

        def fail_write(_: Path, __: dict[str, object]) -> None:
            raise OSError('write failure')

        monkeypatch.setattr(comparison, 'write_json', fail_write)
    else:
        original_replace = Path.replace

        def fail_temporary_replace(path: Path, target: Path) -> Path:
            if path.name.endswith('.tmp'):
                raise OSError('replace failure')
            return original_replace(path, target)

        monkeypatch.setattr(Path, 'replace', fail_temporary_replace)

    with pytest.raises(HarnessError, match=failure):
        _ = comparison.collect(repetitions=5, out=destination.parent, command=(str(child), '{report}'))

    assert destination.read_text(encoding='utf-8') == '{"existing": true}\n'
