import json
from pathlib import Path

import pytest

import benchmarks.harness.comparison as comparison
from benchmarks.harness import HarnessError


def _child(path: Path) -> Path:
    script = path / 'write_report.py'
    script.write_text(
        """import json
import os
import sys

report = sys.argv[1]
order = os.environ['DEPIN_COMPARISON_ORDER']
with open(report, 'w', encoding='utf-8') as stream:
    json.dump({'benchmarks': [
        {'name': 'test_comparison[resolve-depin]', 'stats': {
            'rounds': 1000, 'min': 1.0, 'median': 2.0, 'mean': 2.0, 'stddev': 0.0, 'iqr': 0.0,
        }},
        {'name': 'test_comparison[resolve-wireup-2.12.0]', 'stats': {
            'rounds': 1000, 'min': 3.0, 'median': 4.0, 'mean': 4.0, 'stddev': 0.0, 'iqr': 0.0,
        }},
    ]}, stream)
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
        'environment': {'host': 'synthetic'},
        'harness_revision': 'source-revision',
        'pins': {'pydepin': '0.17.1', 'wireup': '2.12.0'},
        'repetitions': [
            {
                'duration': 6000.0,
                'medians': {'test_comparison[resolve-depin]': 2.0, 'test_comparison[resolve-wireup-2.12.0]': 4.0},
                'order': order,
                'rounds': {'test_comparison[resolve-depin]': 1000, 'test_comparison[resolve-wireup-2.12.0]': 1000},
            }
            for order in ('forward', 'reverse', 'forward', 'reverse', 'forward')
        ],
        'source_revision': 'source-revision',
        'targets': {'resolve': {'target': {'seconds': 0.1}}},
    }
    assert json.loads((tmp_path / 'out' / 'comparison.json').read_text(encoding='utf-8')) == dataset
    assert not list((tmp_path / 'out').glob('*.report.json'))


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
