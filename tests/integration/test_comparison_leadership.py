import hashlib
import json
import math
from pathlib import Path

import pytest

import benchmarks.comparison.collection as comparison
import benchmarks.comparison.leadership as leadership
from benchmarks.comparison import protocol
from benchmarks.harness import HarnessError, require_array, require_number, require_object

EXPECTED_IDS = {'resolve-depin', 'resolve-wireup-2.12.0'}
BUDGETS = Path('benchmarks/budgets.toml')
BASELINE_REVISION = 'a' * 40
REAL_DETERMINISTIC = comparison.collect_deterministic
REAL_BASELINE_VALIDATION = protocol.validate_baseline_archive


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
        'deterministic': {
            'budget_contract': {
                'path': str(BUDGETS),
                'sha256': hashlib.sha256(BUDGETS.read_bytes()).hexdigest(),
            }
        },
        'environment': {
            'host': {
                'available_processors': 1,
                'cpu_model': 'synthetic-cpu',
                'machine': 'synthetic-machine',
                'processor': 'synthetic-processor',
                'system': 'synthetic-system',
            },
            'interpreter': {
                'free_threading': False,
                'hash_randomization': True,
                'implementation': 'CPython',
                'version': '3.12.0',
            },
            'python_hash_seed': '0',
        },
        'harness_revision': 'harness-revision',
        'pins': {'pydepin': '0.17.1', 'wireup': '2.12.0'},
        'protocol': protocol.COMPARISON_PROTOCOL,
        'schema_version': 1,
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


def _calibration(dataset: dict[str, object], *, allowance: float = 0.01, eligible: bool = True) -> dict[str, object]:
    calibration = leadership.calibrate(dataset)
    workloads = require_object(calibration['workloads'], 'calibration.workloads')
    workloads['resolve'] = {'allowance': allowance, 'eligible': eligible, 'p99': allowance}
    return calibration


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


def test_leadership_selects_the_fastest_equivalent_and_excludes_partial_candidates() -> None:
    dataset = _leadership_dataset(
        competitors={
            'slow-1': ('equivalent', (1.2,) * 5),
            'fast-1': ('equivalent', (1.0,) * 5),
            'partial-1': ('partial', (0.1,) * 5),
        }
    )

    verdict = leadership.evaluate(dataset, _calibration(dataset), BUDGETS)[0]

    assert verdict.competitor is not None
    assert verdict.competitor.label == 'fast-1'
    assert verdict.status is leadership.Status.LEADER


def test_leadership_uses_the_confidence_upper_bound_against_the_allowance() -> None:
    dataset = _leadership_dataset(depin=(1.01,) * 5)

    verdict = leadership.evaluate(dataset, _calibration(dataset, allowance=0.005), BUDGETS)[0]

    assert verdict.status is leadership.Status.LOSS
    assert verdict.competitor is not None
    assert verdict.competitor.paired.high > 0.005


def test_leadership_direct_overhead_uses_the_lower_target_ceiling() -> None:
    dataset = _leadership_dataset(target={'fixed_seconds': 0.9, 'fraction_of_direct': 0.5})

    verdict = leadership.evaluate(dataset, _calibration(dataset), BUDGETS)[0]

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
        _ = leadership.evaluate(dataset, _calibration(_leadership_dataset()), BUDGETS)


def test_leadership_refuses_a_required_secondary_metric_without_its_reading() -> None:
    dataset = _leadership_dataset()
    target = require_object(dataset['targets'], 'dataset.targets')['resolve']
    description = require_object(target, 'dataset.targets.resolve')
    description['secondary_metrics'] = ['allocations']

    with pytest.raises(HarnessError, match='secondary'):
        _ = leadership.evaluate(dataset, _calibration(dataset), BUDGETS)


def test_leadership_evaluates_all_outcomes_expanded_from_allocations(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets)

    verdict = leadership.evaluate(dataset, _calibration(dataset), budgets)[0]

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
        _ = leadership.evaluate(dataset, _calibration(dataset), budgets)


def test_leadership_refuses_a_head_deterministic_revision_that_differs_from_the_dataset(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets)
    dataset['source_revision'] = 'other-head'

    with pytest.raises(HarnessError, match=r'head\.source_revision'):
        _ = leadership.evaluate(dataset, _calibration(dataset), budgets)


def test_leadership_fails_an_allocations_claim_when_the_expanded_work_outcome_grows(tmp_path: Path) -> None:
    budgets = _deterministic_budget(tmp_path / 'budgets.toml')
    dataset = _leadership_dataset()
    description = require_object(require_object(dataset['targets'], 'targets')['resolve'], 'resolve')
    description['secondary_metrics'] = ['allocations']
    dataset['deterministic'] = _allocation_evidence(budgets, head_work=13)

    verdict = leadership.evaluate(dataset, _calibration(dataset), budgets)[0]

    assert verdict.status is leadership.Status.REGRESSION
    assert verdict.secondary_passed is False


def test_calibration_writes_a_versioned_protocol_provenance() -> None:
    dataset = _leadership_dataset()

    calibration = leadership.calibrate(dataset)

    assert calibration['schema_version'] == 1
    provenance = require_object(calibration['provenance'], 'calibration.provenance')
    assert provenance['version'] == 1
    assert isinstance(provenance['null_dataset_sha256'], str)
    assert isinstance(provenance['protocol_fingerprint'], str)


@pytest.mark.parametrize('version', [None, True, 0, 2])
def test_calibration_rejects_an_unsupported_comparison_schema_version(version: object) -> None:
    dataset = _leadership_dataset()
    if version is None:
        del dataset['schema_version']
    else:
        dataset['schema_version'] = version

    with pytest.raises(HarnessError, match='schema_version'):
        _ = leadership.calibrate(dataset)


@pytest.mark.parametrize('version', [None, True, 0, 2])
def test_evaluation_rejects_an_unsupported_calibration_schema_version(version: object) -> None:
    dataset = _leadership_dataset()
    calibration = leadership.calibrate(dataset)
    if version is None:
        del calibration['schema_version']
    else:
        calibration['schema_version'] = version

    with pytest.raises(HarnessError, match='schema_version'):
        _ = leadership.evaluate(dataset, calibration, BUDGETS)


def test_evaluation_rejects_a_calibration_from_a_different_protocol() -> None:
    dataset = _leadership_dataset()
    dataset['schema_version'] = 1
    calibration = leadership.calibrate(dataset)
    changed = json.loads(json.dumps(dataset))
    changed_pins = require_object(changed.setdefault('pins', {}), 'changed.pins')
    changed_pins['wireup'] = 'different'

    with pytest.raises(HarnessError, match=r'protocol\.pins\.wireup'):
        _ = leadership.evaluate(changed, calibration, BUDGETS)


def test_evaluation_accepts_seed_shaped_source_and_harness_revisions() -> None:
    dataset = _leadership_dataset()
    null = _leadership_dataset(direct=(0.9,) * 5, depin=(0.9,) * 5)
    calibration = leadership.calibrate(null)
    seed = json.loads(json.dumps(dataset))
    seed['source_revision'] = 'seed-source-revision'
    seed['harness_revision'] = 'seed-harness-revision'

    assert leadership.evaluate(seed, calibration, BUDGETS)[0].status is leadership.Status.LEADER
