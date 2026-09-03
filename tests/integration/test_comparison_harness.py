import hashlib
import inspect
import json
import math
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import benchmarks.harness.comparison as comparison
import benchmarks.harness.leadership as leadership
from benchmarks.comparison import WORKLOADS as COMPARATIVE_WORKLOADS
from benchmarks.contracts import Metric
from benchmarks.harness import HarnessError, reduce, require_array, require_number, require_object

EXPECTED_IDS = {'resolve-depin', 'resolve-wireup-2.12.0'}
BUDGETS = Path('benchmarks/budgets.toml')
REAL_DETERMINISTIC = comparison.collect_deterministic


@pytest.fixture(autouse=True)
def deterministic_children(monkeypatch: pytest.MonkeyPatch) -> None:
    def baseline(directory: Path) -> str:
        return 'baseline-revision'

    def deterministic(directory: Path, report: Path, *, side: str, timeout_seconds: float) -> dict[str, object]:
        return {}

    monkeypatch.setattr(comparison, '_baseline_preflight', baseline)
    monkeypatch.setattr(comparison, 'collect_deterministic', deterministic)


def _collect(
    *,
    out: Path,
    repetitions: int,
    allow_dirty: bool = False,
    command: tuple[str, ...] = comparison.COMMAND,
    timeout_seconds: int | float = comparison.DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    return comparison.collect(
        repetitions=repetitions,
        out=out,
        baseline_dir=out.parent,
        budgets=BUDGETS,
        allow_dirty=allow_dirty,
        command=command,
        timeout_seconds=timeout_seconds,
    )


def test_collection_requires_explicit_baseline_and_budget_inputs() -> None:
    parameters = inspect.signature(comparison.collect).parameters

    assert parameters['baseline_dir'].default is inspect.Parameter.empty
    assert parameters['budgets'].default is inspect.Parameter.empty


def test_collection_cli_passes_an_explicit_null_mode_to_the_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    collected: list[bool] = []

    def collect(
        *,
        repetitions: int,
        out: Path,
        baseline_dir: Path,
        budgets: Path,
        null: bool = False,
        allow_dirty: bool = False,
        command: Sequence[str] = comparison.COMMAND,
        timeout_seconds: int | float = comparison.DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        _ = repetitions, out, baseline_dir, budgets, allow_dirty, command, timeout_seconds
        collected.append(null)
        return {}

    monkeypatch.setattr(comparison, 'collect', collect)

    assert (
        comparison.main(
            ('collect', '--null', '--out', '/tmp/null', '--baseline-dir', '/tmp/base', '--budgets', 'budgets.toml')
        )
        == 0
    )
    assert collected == [True]


def _leadership_dataset(
    *,
    depin: tuple[float, ...] = (0.9, 0.9, 0.9, 0.9, 0.9),
    direct: tuple[float, ...] = (0.4, 0.4, 0.4, 0.4, 0.4),
    competitors: dict[str, tuple[str, tuple[float, ...]]] | None = None,
    target: dict[str, float] | None = None,
    qualified: bool = True,
) -> dict[str, object]:
    candidates = competitors or {'wireup-2.12.0': ('equivalent', (1.0, 1.0, 1.0, 1.0, 1.0))}
    names = {'depin': depin, 'direct': direct} | {label: values for label, (_, values) in candidates.items()}
    repetitions: list[dict[str, object]] = []
    for index in range(len(depin)):
        samples = {
            f'test_comparison[resolve-{label}]': {
                'median': values[index],
                'mean': values[index],
                'rounds': 1000 if qualified else 1,
            }
            for label, values in names.items()
        }
        repetitions.append(
            {
                'medians': {name: sample['median'] for name, sample in samples.items()},
                'rounds': {name: sample['rounds'] for name, sample in samples.items()},
                'samples': samples,
            }
        )
    return {
        'accepted': True,
        'source_revision': 'head-revision',
        'repetitions': repetitions,
        'seed': 17,
        'targets': {
            'resolve': {
                'candidates': [
                    {'classification': classification, 'label': label, 'reason': 'synthetic'}
                    for label, (classification, _) in candidates.items()
                ],
                'target': target or {'fixed_seconds': 1.0, 'fraction_of_direct': None},
            }
        },
    }


def _calibration(*, allowance: float = 0.01, eligible: bool = True) -> dict[str, object]:
    return {'workloads': {'resolve': {'allowance': allowance, 'eligible': eligible, 'p99': allowance}}}


def _deterministic_budget(path: Path) -> Path:
    path.write_text(
        """[[budget]]
workload = "resolve"
metric = "allocations"
limit = 0.0
noise = "low"
justification = "deterministic"

[[budget]]
workload = "resolve"
metric = "work"
limit = 0.0
noise = "low"
justification = "deterministic"
""",
        encoding='utf-8',
    )
    return path


def _allocation_evidence(budgets: Path, *, head_work: int = 12) -> dict[str, object]:
    return {
        'budget_contract': {'path': str(budgets), 'sha256': hashlib.sha256(budgets.read_bytes()).hexdigest()},
        'base': {
            'source_revision': 'base-revision',
            'readings': {'allocations': {'resolve': {'blocks': 4, 'size': 320}}, 'work': {'resolve': 12}},
        },
        'head': {
            'source_revision': 'head-revision',
            'readings': {'allocations': {'resolve': {'blocks': 4, 'size': 320}}, 'work': {'resolve': head_work}},
        },
    }


@pytest.mark.parametrize(
    ('dataset', 'calibration', 'status'),
    [
        (_leadership_dataset(), _calibration(), 'leader'),
        (
            _leadership_dataset(depin=(1.0,) * 5),
            _calibration(),
            'shared-leader',
        ),
        (
            _leadership_dataset(depin=(1.2,) * 5),
            _calibration(),
            'loss',
        ),
        (
            _leadership_dataset(target={'fixed_seconds': 0.5, 'fraction_of_direct': 0.5}),
            _calibration(),
            'absolute-failure',
        ),
        (_leadership_dataset(qualified=False), _calibration(), 'unstable'),
        (
            _leadership_dataset(competitors={'wireup-2.12.0': ('partial', (0.1,) * 5)}),
            _calibration(),
            'no-equivalent-competitor',
        ),
    ],
)
def test_leadership_evaluates_each_workload_status(
    dataset: dict[str, object], calibration: dict[str, object], status: str
) -> None:
    verdict = leadership.evaluate(dataset, calibration, BUDGETS)[0]

    assert verdict.status.value == status


def test_leadership_selects_the_fastest_equivalent_and_excludes_partial_candidates() -> None:
    dataset = _leadership_dataset(
        competitors={
            'slow-1': ('equivalent', (1.2,) * 5),
            'fast-1': ('equivalent', (1.0,) * 5),
            'partial-1': ('partial', (0.1,) * 5),
        }
    )

    verdict = leadership.evaluate(dataset, _calibration(), BUDGETS)[0]

    assert verdict.competitor is not None
    assert verdict.competitor.label == 'fast-1'
    assert verdict.status is leadership.Status.LEADER


def test_leadership_uses_the_confidence_upper_bound_against_the_allowance() -> None:
    dataset = _leadership_dataset(depin=(1.01,) * 5)

    verdict = leadership.evaluate(dataset, _calibration(allowance=0.005), BUDGETS)[0]

    assert verdict.status is leadership.Status.LOSS
    assert verdict.competitor is not None
    assert verdict.competitor.paired.high > 0.005


def test_leadership_direct_overhead_uses_the_lower_target_ceiling() -> None:
    dataset = _leadership_dataset(target={'fixed_seconds': 0.9, 'fraction_of_direct': 0.5})

    verdict = leadership.evaluate(dataset, _calibration(), BUDGETS)[0]

    assert verdict.absolute_ceiling == 0.2
    assert verdict.absolute_overhead == 0.5
    assert verdict.absolute_passed is False


def test_leadership_marks_a_null_p99_above_five_percent_unstable_without_clamping() -> None:
    dataset = _leadership_dataset()
    null = _leadership_dataset(depin=(1.0, 1.0, 1.0, 1.0, 1.0), direct=(0.9, 1.1, 0.9, 1.1, 0.9))

    calibration = leadership.calibrate(null)
    verdict = leadership.evaluate(dataset, calibration, BUDGETS)[0]

    workloads = require_object(calibration['workloads'], 'calibration.workloads')
    resolve = require_object(workloads['resolve'], 'calibration.workloads.resolve')
    assert require_number(resolve['p99'], 'calibration.workloads.resolve.p99') > 0.05
    assert resolve['eligible'] is False
    assert verdict.status is leadership.Status.UNSTABLE


def test_calibration_preserves_raw_p99_before_rounding_to_the_next_milliunit() -> None:
    dataset = _leadership_dataset(depin=(0.99, 1.01, 0.98, 1.02, 1.0))

    calibration = leadership.calibrate(dataset)
    entry = require_object(require_object(calibration['workloads'], 'workloads')['resolve'], 'resolve')
    p99 = require_number(entry['p99'], 'p99')
    allowance = require_number(entry['allowance'], 'allowance')

    assert allowance == pytest.approx(math.ceil(p99 / 0.001) * 0.001)
    assert allowance >= p99


def test_calibration_marks_four_qualified_pairs_as_insufficient_and_evaluation_unstable() -> None:
    dataset = _leadership_dataset()
    repetitions = require_array(dataset['repetitions'], 'repetitions')
    samples = require_object(require_object(repetitions[-1], 'repetition')['samples'], 'samples')
    require_object(samples['test_comparison[resolve-depin]'], 'depin')['rounds'] = 1
    require_object(samples['test_comparison[resolve-direct]'], 'direct')['rounds'] = 1

    calibration = leadership.calibrate(dataset)
    entry = require_object(require_object(calibration['workloads'], 'workloads')['resolve'], 'resolve')

    assert entry == {'allowance': None, 'eligible': False, 'p99': None}
    assert leadership.evaluate(dataset, calibration, BUDGETS)[0].status is leadership.Status.UNSTABLE


@pytest.mark.parametrize(
    ('entry', 'message'),
    [
        ({'p99': -0.001, 'allowance': 0.0, 'eligible': True}, 'p99'),
        ({'p99': 0.01, 'allowance': 0.011, 'eligible': True}, 'rounded'),
        ({'p99': 0.05, 'allowance': 0.05, 'eligible': False}, 'eligible'),
    ],
)
def test_calibration_entries_fail_closed_on_invalid_or_inconsistent_values(
    entry: dict[str, object], message: str
) -> None:
    with pytest.raises(HarnessError, match=message):
        _ = leadership.evaluate(_leadership_dataset(), {'workloads': {'resolve': entry}}, BUDGETS)


@pytest.mark.parametrize(
    ('dataset', 'calibration', 'expected'),
    [
        (_leadership_dataset(), _calibration(), 0),
        (_leadership_dataset(depin=(1.2,) * 5), _calibration(), 1),
        (_leadership_dataset(qualified=False), _calibration(), 3),
    ],
)
def test_leadership_evaluate_cli_returns_the_documented_exit_status(
    tmp_path: Path, dataset: dict[str, object], calibration: dict[str, object], expected: int
) -> None:
    dataset_path = tmp_path / 'comparison.json'
    calibration_path = tmp_path / 'calibration.json'
    dataset_path.write_text(json.dumps(dataset), encoding='utf-8')
    calibration_path.write_text(json.dumps(calibration), encoding='utf-8')

    assert (
        leadership.main(
            ('evaluate', str(dataset_path), '--calibration', str(calibration_path), '--budgets', str(BUDGETS))
        )
        == expected
    )


def test_leadership_cli_returns_two_for_malformed_input(tmp_path: Path) -> None:
    malformed = tmp_path / 'comparison.json'
    malformed.write_text('{}', encoding='utf-8')

    assert leadership.main(('calibrate', str(malformed), '--out', str(tmp_path / 'calibration.json'))) == 2


@pytest.mark.parametrize('accepted', [False, None, 'true'])
def test_leadership_refuses_diagnostic_or_missing_acceptance(accepted: object) -> None:
    dataset = _leadership_dataset()
    if accepted is None:
        dataset.pop('accepted')
    else:
        dataset['accepted'] = accepted

    with pytest.raises(HarnessError, match='allow-dirty'):
        _ = leadership.calibrate(dataset)
    with pytest.raises(HarnessError, match='allow-dirty'):
        _ = leadership.evaluate(dataset, _calibration(), BUDGETS)


@pytest.mark.parametrize(
    ('label', 'classification', 'message'),
    [('other', 'typo', 'invalid'), ('direct', 'equivalent', 'reserved'), ('same', 'equivalent', 'duplicated')],
)
def test_leadership_refuses_invalid_candidate_contracts(label: str, classification: str, message: str) -> None:
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['candidates'] = (
        [
            {'label': label, 'classification': classification, 'reason': 'synthetic'},
            {'label': label, 'classification': 'partial', 'reason': 'synthetic'},
        ]
        if message == 'duplicated'
        else [{'label': label, 'classification': classification, 'reason': 'synthetic'}]
    )

    with pytest.raises(HarnessError, match=message):
        _ = leadership.evaluate(dataset, _calibration(), BUDGETS)


def test_leadership_refuses_a_required_secondary_metric_without_its_reading() -> None:
    dataset = _leadership_dataset()
    target = require_object(dataset['targets'], 'dataset.targets')['resolve']
    description = require_object(target, 'dataset.targets.resolve')
    description['secondary_metrics'] = ['allocations']

    with pytest.raises(HarnessError, match='secondary'):
        _ = leadership.evaluate(dataset, _calibration(), BUDGETS)


def test_leadership_evaluates_all_outcomes_expanded_from_allocations(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets)

    verdict = leadership.evaluate(dataset, _calibration(), budgets)[0]

    assert verdict.secondary_passed is True
    assert [(outcome.metric, outcome.outcome.value) for outcome in verdict.secondary_verdicts] == [
        ('allocations', 'pass'),
        ('work', 'pass'),
    ]


def test_leadership_refuses_a_divergent_deterministic_budget_digest(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    evidence = _allocation_evidence(budgets)
    require_object(evidence['budget_contract'], 'budget_contract')['sha256'] = '0' * 64
    dataset['deterministic'] = evidence

    with pytest.raises(HarnessError, match='digest'):
        _ = leadership.evaluate(dataset, _calibration(), budgets)


def test_leadership_refuses_a_head_deterministic_revision_that_differs_from_the_dataset(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets)
    dataset['source_revision'] = 'other-head'

    with pytest.raises(HarnessError, match=r'head\.source_revision'):
        _ = leadership.evaluate(dataset, _calibration(), budgets)


def test_leadership_fails_an_allocations_claim_when_the_expanded_work_outcome_grows(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets, head_work=13)

    verdict = leadership.evaluate(dataset, _calibration(), budgets)[0]

    assert verdict.status is leadership.Status.REGRESSION
    assert verdict.secondary_passed is False


def test_comparison_descriptions_serialize_declared_secondary_metrics() -> None:
    descriptions = comparison.descriptions()

    assert set(descriptions) == {comparative.workload.name for comparative in COMPARATIVE_WORKLOADS}
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
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, 'descriptions', lambda: _leadership_dataset()['targets'])

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
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'cwd': os.getcwd(), 'pythonpath': os.environ['PYTHONPATH']}))"
    )
    monkeypatch.setattr(comparison, 'DETERMINISTIC_COMMAND', ('-c', script, '{report}'))
    readings = REAL_DETERMINISTIC(tmp_path, tmp_path / 'deterministic.json', side='base', timeout_seconds=0.25)

    assert readings == {'cwd': str(tmp_path), 'pythonpath': str(tmp_path)}


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
    calls = tmp_path / 'calls.txt'
    monkeypatch.setenv('CALL_LOG', str(calls))
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1', 'wireup': '2.12.0'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
    monkeypatch.setattr(comparison, '_environment', lambda: {'host': 'synthetic'})
    monkeypatch.setattr(comparison, 'descriptions', lambda: {'resolve': {'target': {'seconds': 0.1}}})

    dataset = _collect(
        repetitions=5,
        out=tmp_path / 'out',
        command=(str(child), '{report}'),
    )

    assert calls.read_text(encoding='utf-8').splitlines() == ['forward', 'reverse', 'forward', 'reverse', 'forward']
    assert dataset == {
        'accepted': True,
        'collection_command': f'python {child} {{report}}',
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
        'seed': 20260902,
        'deterministic': {
            'budget_contract': {
                'path': 'benchmarks/budgets.toml',
                'sha256': hashlib.sha256(BUDGETS.read_bytes()).hexdigest(),
            },
            'base': {'source_revision': 'baseline-revision', 'readings': {}},
            'head': {'source_revision': 'source-revision', 'readings': {}},
        },
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
        _ = _collect(repetitions=5, out=tmp_path / 'out', command=('-c', 'raise SystemExit(3)'))

    assert not (tmp_path / 'out').exists()


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
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)
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
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

    with pytest.raises(HarnessError, match='exited 23'):
        _ = _collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))

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
        ('nan_data', r'data\[0\]'),
        ('negative_data', r'data\[0\]'),
        ('infinite_data', r'data\[0\]'),
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
        _ = _collect(repetitions=5, out=tmp_path / 'out', command=(str(child), '{report}'))


def test_collection_times_out_a_blocked_child_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    child = tmp_path / 'blocked.py'
    child.write_text("import signal\nprint('blocked-marker', flush=True)\nsignal.pause()\n", encoding='utf-8')
    monkeypatch.setattr(comparison, '_revision', lambda: 'source-revision')
    monkeypatch.setattr(comparison, '_expected_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_pins', lambda: {'pydepin': '0.17.1'})
    monkeypatch.setattr(comparison, '_clean_tree', lambda: True)
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

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
    monkeypatch.setattr(comparison, '_expected_ids', lambda: EXPECTED_IDS)

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
        _ = _collect(repetitions=5, out=destination.parent, command=(str(child), '{report}'))

    assert destination.read_text(encoding='utf-8') == '{"existing": true}\n'
    assert not (destination.parent / '.comparison.json.tmp').exists()
