import hashlib
import inspect
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import benchmarks.comparison.collection as comparison
import benchmarks.comparison.leadership as leadership
from benchmarks.comparison import WORKLOADS as COMPARATIVE_WORKLOADS
from benchmarks.comparison import protocol
from benchmarks.comparison.inventory import build
from benchmarks.contracts import Metric
from benchmarks.harness import HarnessError, reduce, require_array, require_object

EXPECTED_IDS = {'resolve-depin', 'resolve-wireup-2.12.0'}
BUDGETS = Path('benchmarks/budgets.toml')
BASELINE_REVISION = 'a' * 40
REAL_DETERMINISTIC = comparison.collect_deterministic
REAL_BASELINE_VALIDATION = protocol.validate_baseline_archive


def _skip_baseline_validation(directory: Path, revision: str) -> None:
    _ = directory, revision


@pytest.fixture(autouse=True)
def deterministic_children(monkeypatch: pytest.MonkeyPatch) -> None:
    def deterministic(directory: Path, report: Path, *, side: str, timeout_seconds: float) -> dict[str, object]:
        return {}

    monkeypatch.setattr(comparison, 'collect_deterministic', deterministic)
    monkeypatch.setattr(protocol, 'validate_baseline_archive', _skip_baseline_validation)


def _collect(
    *,
    out: Path,
    repetitions: int,
    baseline_dir: Path | None = None,
    allow_dirty: bool = False,
    command: tuple[str, ...] = comparison.COMMAND,
    timeout_seconds: int | float = comparison.DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    base = baseline_dir or out.parent
    base.mkdir(parents=True, exist_ok=True)
    (base / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    return comparison.collect(
        repetitions=repetitions,
        out=out,
        baseline_dir=base,
        baseline_revision=BASELINE_REVISION,
        budgets=BUDGETS,
        allow_dirty=allow_dirty,
        command=command,
        timeout_seconds=timeout_seconds,
    )


def test_collection_requires_explicit_baseline_revision_and_budget_inputs() -> None:
    parameters = inspect.signature(comparison.collect).parameters

    assert parameters['baseline_dir'].default is inspect.Parameter.empty
    assert parameters['baseline_revision'].default is inspect.Parameter.empty
    assert parameters['budgets'].default is inspect.Parameter.empty


def test_null_collection_expects_only_direct_and_depin_report_ids() -> None:
    expected = {
        f'{comparative.workload.name}-{implementation.label}'
        for comparative in build()
        if comparative.target is not None
        for implementation in (comparative.workload.subject, comparative.workload.baseline)
        if implementation is not None
    }

    assert comparison.expected_ids(null=True) == expected
    assert comparison.expected_ids(null=True) < comparison.expected_ids()


def test_collector_limits_comparative_evidence_to_the_twenty_three_authored_targets() -> None:
    targeted = tuple(comparative for comparative in COMPARATIVE_WORKLOADS if comparative.target is not None)

    assert len(targeted) == 23
    assert len(comparison.expected_ids(null=True)) == 46
    assert set(comparison.descriptions()) == {comparative.workload.name for comparative in targeted}


def test_focused_collection_limits_the_expected_matrix_to_one_declared_workload() -> None:
    expected = {
        'resolve_cached_singleton-depin',
        'resolve_cached_singleton-direct',
        'resolve_cached_singleton-dependency-injector-4.49.1',
        'resolve_cached_singleton-dishka-1.10.1',
        'resolve_cached_singleton-wireup-2.12.0',
        'resolve_cached_singleton-svcs-26.1.0',
    }

    assert comparison.expected_ids(focus=('resolve_cached_singleton',)) == expected


def test_collection_cli_passes_an_explicit_null_mode_to_the_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    collected: list[bool] = []

    def collect(
        *,
        repetitions: int,
        out: Path,
        baseline_dir: Path,
        baseline_revision: str,
        budgets: Path,
        null: bool = False,
        focus: Sequence[str] = (),
        allow_dirty: bool = False,
        command: Sequence[str] = comparison.COMMAND,
        timeout_seconds: int | float = comparison.DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        _ = repetitions, out, baseline_dir, baseline_revision, budgets, focus, allow_dirty, command, timeout_seconds
        collected.append(null)
        return {}

    monkeypatch.setattr(comparison, 'collect', collect)

    assert (
        comparison.main(
            (
                'collect',
                '--null',
                '--out',
                '/tmp/null',
                '--baseline-dir',
                '/tmp/base',
                '--baseline-revision',
                BASELINE_REVISION,
                '--budgets',
                'budgets.toml',
            )
        )
        == 0
    )
    assert collected == [True]


@pytest.mark.parametrize('revision', ['', ' ' * 40, 'not-a-sha', 'a' * 39])
def test_collection_refuses_missing_or_malformed_baseline_revisions(tmp_path: Path, revision: str) -> None:
    with pytest.raises(HarnessError, match='baseline revision'):
        _ = comparison.collect(
            repetitions=5,
            out=tmp_path / 'out',
            baseline_dir=tmp_path,
            baseline_revision=revision,
            budgets=BUDGETS,
        )


def test_comparison_descriptions_serialize_declared_secondary_metrics() -> None:
    descriptions = comparison.descriptions()

    assert set(descriptions) == {
        comparative.workload.name for comparative in COMPARATIVE_WORKLOADS if comparative.target is not None
    }
    assert all(
        require_object(description, 'description').get('secondary_metrics') is not None
        for description in descriptions.values()
    )
    assert {
        name
        for name, description in descriptions.items()
        if require_array(
            require_object(description, f'descriptions.{name}').get('secondary_metrics'), f'{name}.metrics'
        )
    } == {
        comparative.workload.name
        for comparative in COMPARATIVE_WORKLOADS
        if comparative.target is not None
        if comparative.workload.claim.metric is not Metric.LATENCY
    }


def test_collector_output_flows_directly_into_leadership_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child(tmp_path)
    monkeypatch.setenv('CALL_LOG', str(tmp_path / 'calls.txt'))
    monkeypatch.setattr(comparison, '_revision', lambda: 'head-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(
        comparison,
        'descriptions',
        lambda: {
            'resolve': {
                'candidates': [{'classification': 'equivalent', 'label': 'wireup-2.12.0', 'reason': 'synthetic'}],
                'target': {'fixed_seconds': 1.0, 'fraction_of_direct': None},
            }
        },
    )

    dataset = _collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))

    verdict = leadership.evaluate(dataset, leadership.calibrate(dataset), BUDGETS)[0]

    assert dataset['seed'] == 20260902
    assert verdict.status is leadership.Status.UNSTABLE


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
elif mutation == 'nan_data':
    benchmarks[0]['stats']['data'][0] = float('nan')
elif mutation == 'negative_data':
    benchmarks[0]['stats']['data'][0] = -1.0
elif mutation == 'infinite_data':
    benchmarks[0]['stats']['data'][0] = float('inf')
with open(report, 'w', encoding='utf-8') as stream:
    json.dump({'benchmarks': benchmarks}, stream)
with open(os.environ['CALL_LOG'], 'a', encoding='utf-8') as stream:
    stream.write(order + '\\n')
""",
        encoding='utf-8',
    )
    return script


def test_deterministic_child_uses_the_side_directory_environment_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = (
        'import json, os, pathlib, sys; '
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'cwd': os.getcwd(), 'pythonpath': os.environ['PYTHONPATH'], "
        "'write_bytecode': os.environ['PYTHONDONTWRITEBYTECODE']}))"
    )
    monkeypatch.setattr(comparison, 'DETERMINISTIC_COMMAND', ('-c', script, '{report}'))
    readings = REAL_DETERMINISTIC(tmp_path, tmp_path / 'deterministic.json', side='base', timeout_seconds=0.25)

    assert readings == {'cwd': str(tmp_path), 'pythonpath': str(tmp_path), 'write_bytecode': '1'}


def test_deterministic_child_does_not_write_bytecode_into_an_archived_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / 'archived_module.py').write_text('VALUE = 1\n', encoding='utf-8')
    script = (
        'import archived_module, json, pathlib, sys; '
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'value': archived_module.VALUE}))"
    )
    monkeypatch.setattr(comparison, 'DETERMINISTIC_COMMAND', ('-c', script, '{report}'))

    readings = REAL_DETERMINISTIC(tmp_path, tmp_path / 'deterministic.json', side='base', timeout_seconds=0.25)

    assert readings == {'value': 1}
    assert not list(tmp_path.rglob('__pycache__'))


def test_deterministic_child_forwards_its_timeout_and_names_the_failed_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[float] = []

    def run(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        observed.append(timeout)
        raise subprocess.TimeoutExpired(argv, timeout, output='child-output', stderr='child-error')

    monkeypatch.setattr(subprocess, 'run', run)

    with pytest.raises(HarnessError, match=r'(?s)base deterministic child timed out.*child-output'):
        _ = REAL_DETERMINISTIC(tmp_path, tmp_path / 'report.json', side='base', timeout_seconds=0.125)

    assert observed == [0.125]


def test_collection_counterbalances_children_and_reduces_their_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child(tmp_path)
    archive = tmp_path / 'archive'
    archive.mkdir()
    (archive / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    calls = tmp_path / 'calls.txt'
    monkeypatch.setenv('CALL_LOG', str(calls))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, '_environment', lambda: {'host': 'synthetic'})
    monkeypatch.setattr(comparison, 'descriptions', lambda: {'resolve': {'target': {'seconds': 0.1}}})

    dataset = _collect(
        repetitions=5,
        out=tmp_path / 'out',
        baseline_dir=archive,
        command=(str(child), '{report}'),
    )

    assert calls.read_text(encoding='utf-8').splitlines() == ['forward', 'reverse', 'forward', 'reverse', 'forward']
    assert dataset == {
        'accepted': True,
        'collection_command': f'python {child} {{report}}',
        'environment': {'host': 'synthetic', 'python_hash_seed': '0'},
        'harness_revision': 'source-revision',
        'pins': {'pydepin': '0.17.1', 'wireup': '2.12.0'},
        'protocol': protocol.COMPARISON_PROTOCOL,
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
        'seed': 20260902,
        'schema_version': 1,
        'deterministic': {
            'budget_contract': {
                'path': 'benchmarks/budgets.toml',
                'sha256': hashlib.sha256(BUDGETS.read_bytes()).hexdigest(),
            },
            'base': {'source_revision': BASELINE_REVISION, 'readings': {}},
            'head': {'source_revision': 'source-revision', 'readings': {}},
        },
        'targets': {'resolve': {'target': {'seconds': 0.1}}},
    }
    assert json.loads((tmp_path / 'out' / 'comparison.json').read_text(encoding='utf-8')) == dataset
    assert not list(tmp_path.rglob('report.json'))


@pytest.mark.parametrize('marker', [None, 'b' * 40, f'{BASELINE_REVISION}\nextra\n'])
def test_collection_refuses_an_archive_marker_that_does_not_match_the_claimed_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str | None
) -> None:
    archive = tmp_path / 'archive'
    archive.mkdir()
    if marker is not None:
        (archive / '.depin-baseline-revision').write_text(marker, encoding='utf-8')

    def preflight(*, allow_dirty: bool) -> tuple[str, dict[str, str]]:
        _ = allow_dirty
        return 'head', {}

    monkeypatch.setattr(comparison, '_preflight', preflight)

    def child(*args: object, **kwargs: object) -> dict[str, reduce.Aggregate]:
        raise AssertionError('the child must not run before baseline marker validation')

    monkeypatch.setattr(comparison, '_run', child)

    with pytest.raises(HarnessError, match='baseline marker'):
        _ = comparison.collect(
            repetitions=5,
            out=tmp_path / 'out',
            baseline_dir=archive,
            baseline_revision=BASELINE_REVISION,
            budgets=BUDGETS,
        )


def test_collection_requires_at_least_five_repetitions(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='at least five'):
        _ = _collect(repetitions=4, out=tmp_path)


def test_dirty_collection_is_diagnostic_evidence_when_explicitly_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child(tmp_path)
    monkeypatch.setenv('CALL_LOG', str(tmp_path / 'calls.txt'))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: False)
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, '_environment', lambda: {'host': 'synthetic'})
    monkeypatch.setattr(comparison, 'descriptions', lambda: dict[str, object]())

    dataset = _collect(repetitions=5, out=tmp_path / 'out', allow_dirty=True, command=(str(child), '{report}'))

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
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='exited 23'):
        _ = _collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))

    assert not list(tmp_path.rglob('report.json'))


def test_collection_times_out_a_blocked_child_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    child = tmp_path / 'blocked.py'
    child.write_text("import signal\nprint('blocked-marker', flush=True)\nsignal.pause()\n", encoding='utf-8')
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='blocked-marker') as raised:
        _ = _collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'), timeout_seconds=1)

    assert 'repetition 0 (forward)' in str(raised.value)
    assert str(child) in str(raised.value)
    assert not list(tmp_path.rglob('report.json'))


def test_collection_uses_one_total_deadline_and_refuses_a_second_spawn_after_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[float] = []
    clock = iter((100.0, 101.0, 111.0))

    def monotonic() -> float:
        return next(clock)

    def run(
        _: tuple[str, ...],
        __: Path,
        ___: str,
        *,
        repetition: int,
        timeout_seconds: int | float,
        expected: set[str],
    ) -> dict[str, reduce.Aggregate]:
        calls.append(float(timeout_seconds))
        return {
            'test_comparison[resolve-depin]': reduce.Aggregate(
                'test_comparison[resolve-depin]', 1000, 1.0, 2.0, 2.0, 0.0, 0.0
            ),
            'test_comparison[resolve-wireup-2.12.0]': reduce.Aggregate(
                'test_comparison[resolve-wireup-2.12.0]', 1000, 1.0, 2.0, 2.0, 0.0, 0.0
            ),
        }

    monkeypatch.setattr(comparison, '_monotonic', monotonic)
    monkeypatch.setattr(comparison, '_run', run)
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='before child'):
        _ = _collect(repetitions=5, out=tmp_path / 'out', timeout_seconds=10)

    assert calls == [9.0]


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
    monkeypatch.setattr(comparison, 'expected_ids', lambda: EXPECTED_IDS)
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
        _ = _collect(repetitions=5, out=destination.parent, command=(str(child), '{report}'))

    assert destination.read_text(encoding='utf-8') == '{"existing": true}\n'
    assert not (destination.parent / '.comparison.json.tmp').exists()
