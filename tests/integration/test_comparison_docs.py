import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmarks.harness.comparison_report as comparison_report
from benchmarks.harness import HarnessError, require_array, require_object
from benchmarks.harness.comparison_report import main, render

FIXTURE = Path(__file__).parents[1] / 'fixtures' / 'comparison'
BUDGETS = Path('benchmarks/budgets.toml')
WORKLOAD = 'allocations_of_a_cached_singleton_resolution'
PUBLISHED_DATASET = Path('benchmarks/results/2026-09-02-competitive-baseline/comparison.json')
PUBLISHED_CALIBRATION = Path('benchmarks/results/2026-09-02-competitive-baseline/calibration.json')
PUBLISHED_PAGE = Path('docs/performance/comparison-baseline.md')
Mutation = Callable[[dict[str, object]], None]


def _evidence() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads((FIXTURE / 'accepted.json').read_text(encoding='utf-8')),
        json.loads((FIXTURE / 'calibration.json').read_text(encoding='utf-8')),
    )


def _target(dataset: dict[str, object]) -> dict[str, object]:
    return require_object(require_object(dataset['targets'], 'fixture.targets')[WORKLOAD], 'fixture.workload')


def _candidate(dataset: dict[str, object]) -> dict[str, object]:
    return require_object(require_array(_target(dataset)['candidates'], 'fixture.candidates')[0], 'fixture.candidate')


def _claim_newline(dataset: dict[str, object]) -> None:
    _target(dataset)['claim'] = 'bad\nclaim'


def _reason_control(dataset: dict[str, object]) -> None:
    _candidate(dataset)['reason'] = 'bad\x1freason'


def _label_newline(dataset: dict[str, object]) -> None:
    _candidate(dataset)['label'] = 'bad\nlabel'


def _source_revision_newline(dataset: dict[str, object]) -> None:
    dataset['source_revision'] = 'bad\nrevision'


def _harness_revision_control(dataset: dict[str, object]) -> None:
    dataset['harness_revision'] = 'bad\x1frevision'


def _pin_key_newline(dataset: dict[str, object]) -> None:
    pins = dataset['pins']
    if not isinstance(pins, dict):
        raise AssertionError('fixture pins must be an object')
    pins['bad\nkey'] = '1.0'


def _pin_value_control(dataset: dict[str, object]) -> None:
    pins = dataset['pins']
    if not isinstance(pins, dict):
        raise AssertionError('fixture pins must be an object')
    pins['pydepin'] = 'bad\x1fversion'


def _host_newline(dataset: dict[str, object]) -> None:
    environment = dataset['environment']
    if not isinstance(environment, dict):
        raise AssertionError('fixture environment must be an object')
    environment['host'] = 'bad\nhost'


def _collection_command_newline(dataset: dict[str, object]) -> None:
    dataset['collection_command'] = 'bad\ncommand'


def _harness_revision_boolean(dataset: dict[str, object]) -> None:
    dataset['harness_revision'] = True


def _pin_value_list(dataset: dict[str, object]) -> None:
    pins = dataset['pins']
    if not isinstance(pins, dict):
        raise AssertionError('fixture pins must be an object')
    pins['pydepin'] = []


def _host_object(dataset: dict[str, object]) -> None:
    environment = dataset['environment']
    if not isinstance(environment, dict):
        raise AssertionError('fixture environment must be an object')
    environment['host'] = {}


def _collection_command_list(dataset: dict[str, object]) -> None:
    dataset['collection_command'] = []


def test_comparison_report_renders_evidence_without_aggregate_ranking() -> None:
    dataset, calibration = _evidence()

    rendered = render(dataset, calibration, BUDGETS)

    for expected in (
        'allocations_of_a_cached_singleton_resolution',
        'Claim',
        'What does one resolution allocate once the value is already built?',
        'same observed cached resolution',
        'does not preserve the complete observation',
        'cannot express this cache lifecycle',
        '900.000 ms',
        '[-10.00%, -10.00%]',
        '1.0%',
        '+500.000 ms',
        '1.000 s',
        'allocations: pass',
        'work: pass',
        'leader',
        'head-revision',
        'harness-revision',
        'synthetic-host',
    ):
        assert expected in rendered
    assert rendered.count('—') >= 4
    assert rendered.endswith('\n')
    for forbidden in ('overall winner', 'geometric mean', 'score', 'fastest library'):
        assert forbidden not in rendered.lower()


def test_comparison_report_matches_its_committed_fixture() -> None:
    dataset, calibration = _evidence()

    assert render(dataset, calibration, BUDGETS) == (FIXTURE / 'expected.md').read_text(encoding='utf-8')


def test_published_comparison_page_is_the_exact_render_of_its_dataset() -> None:
    dataset = json.loads(PUBLISHED_DATASET.read_text(encoding='utf-8'))
    calibration = json.loads(PUBLISHED_CALIBRATION.read_text(encoding='utf-8'))

    assert PUBLISHED_PAGE.read_text(encoding='utf-8') == render(dataset, calibration, BUDGETS)


def test_comparison_report_cli_writes_only_markdown_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    status = main(
        (str(FIXTURE / 'accepted.json'), '--calibration', str(FIXTURE / 'calibration.json'), '--budgets', str(BUDGETS))
    )

    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.startswith('# Comparative performance evidence\n')
    assert captured.err == ''


def test_comparison_report_reports_malformed_evidence(capsys: pytest.CaptureFixture[str]) -> None:
    status = main(
        (str(FIXTURE / 'missing.json'), '--calibration', str(FIXTURE / 'calibration.json'), '--budgets', str(BUDGETS))
    )

    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ''
    assert 'missing.json: cannot be read' in captured.err


def test_comparison_report_raises_harness_error_for_invalid_render_input() -> None:
    dataset, calibration = _evidence()
    dataset['accepted'] = False

    with pytest.raises(HarnessError, match='accepted'):
        _ = render(dataset, calibration, BUDGETS)


@pytest.mark.parametrize(
    ('mutate', 'where'),
    [
        (_claim_newline, 'claim'),
        (_reason_control, 'reason'),
        (_label_newline, 'label'),
        (_source_revision_newline, 'source_revision'),
        (_harness_revision_control, 'harness_revision'),
        (_pin_key_newline, 'pins'),
        (_pin_value_control, 'pins'),
        (_host_newline, 'host'),
        (_collection_command_newline, 'collection_command'),
    ],
)
def test_comparison_report_rejects_unsafe_dynamic_markdown_text(mutate: Mutation, where: str) -> None:
    dataset, calibration = _evidence()
    altered = deepcopy(dataset)
    mutate(altered)

    with pytest.raises(HarnessError, match=where):
        _ = render(altered, calibration, BUDGETS)


def test_comparison_report_uses_an_inventory_claim_over_dataset_text(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset, calibration = _evidence()
    workload = WORKLOAD
    _target(dataset)['claim'] = 'fastest library overall winner'
    inventory = (
        SimpleNamespace(workload=SimpleNamespace(name=workload, claim=SimpleNamespace(question='Authoritative claim'))),
    )
    monkeypatch.setattr(comparison_report, 'INVENTORY', inventory)

    with pytest.raises(HarnessError, match='claim'):
        _ = render(dataset, calibration, BUDGETS)


def test_comparison_report_rejects_an_unknown_workload_before_rendering(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset, calibration = _evidence()
    unknown = 'fastest_library_overall'
    description = deepcopy(_target(dataset))
    description['claim'] = 'fastest library overall winner'
    description['secondary_metrics'] = []
    targets = require_object(dataset['targets'], 'fixture.targets')
    targets[unknown] = description
    calibrations = require_object(calibration['workloads'], 'fixture.calibration')
    calibrations[unknown] = deepcopy(calibrations[WORKLOAD])
    dataset_path = tmp_path / 'dataset.json'
    calibration_path = tmp_path / 'calibration.json'
    dataset_path.write_text(json.dumps(dataset), encoding='utf-8')
    calibration_path.write_text(json.dumps(calibration), encoding='utf-8')

    with pytest.raises(HarnessError, match=unknown):
        _ = render(dataset, calibration, BUDGETS)

    status = main((str(dataset_path), '--calibration', str(calibration_path), '--budgets', str(BUDGETS)))

    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ''
    assert unknown in captured.err


@pytest.mark.parametrize(
    ('mutate', 'where'),
    [
        (_harness_revision_boolean, 'harness_revision'),
        (_pin_value_list, 'pins.pydepin'),
        (_host_object, 'environment.host'),
        (_collection_command_list, 'collection_command'),
    ],
)
def test_comparison_report_rejects_non_text_provenance(mutate: Mutation, where: str) -> None:
    dataset, calibration = _evidence()
    altered = deepcopy(dataset)
    mutate(altered)

    with pytest.raises(HarnessError, match=where):
        _ = render(altered, calibration, BUDGETS)


def test_comparison_report_escapes_markdown_structure_in_dynamic_text() -> None:
    dataset, calibration = _evidence()
    _candidate(dataset)['reason'] = r'one\two|`three`'

    rendered = render(dataset, calibration, BUDGETS)

    assert r'one\\two\|\`three\`' in rendered


@pytest.mark.parametrize(
    ('argv', 'message'),
    [
        (
            (
                str(FIXTURE / 'missing.json'),
                '--calibration',
                str(FIXTURE / 'calibration.json'),
                '--budgets',
                str(BUDGETS),
            ),
            'missing.json',
        ),
        (
            (str(FIXTURE / 'accepted.json'), '--calibration', str(FIXTURE / 'missing.json'), '--budgets', str(BUDGETS)),
            'missing.json',
        ),
        (
            (
                str(FIXTURE / 'accepted.json'),
                '--calibration',
                str(FIXTURE / 'calibration.json'),
                '--budgets',
                'missing.toml',
            ),
            'missing.toml',
        ),
    ],
)
def test_comparison_report_cli_rejects_malformed_input(
    argv: tuple[str, ...], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    status = main(argv)

    captured = capsys.readouterr()

    assert status == 2
    assert captured.out == ''
    assert message in captured.err


@pytest.mark.parametrize(
    ('direct', 'depin', 'expected'),
    [
        (1.0, 2.0, '+1.000 s'),
        (2.0, 1.0, '-1.000 s'),
        (1.0, 1.001, '+1.000 ms'),
        (1.001, 1.0, '-1.000 ms'),
        (1.0, 1.0004, '+400.000 µs'),
        (1.0004, 1.0, '-400.000 µs'),
        (1.0, 1.0000004, '+400.000 ns'),
        (1.0, 1.0, '0.000 ns'),
    ],
)
def test_comparison_report_formats_direct_overhead_with_an_adaptive_unit(
    direct: float, depin: float, expected: str
) -> None:
    dataset, calibration = _evidence()
    repetitions = require_array(dataset['repetitions'], 'fixture.repetitions')
    for repetition in repetitions:
        samples = require_object(require_object(repetition, 'fixture.repetition')['samples'], 'fixture.samples')
        for label, value in (('direct', direct), ('depin', depin)):
            sample = samples[f'test_comparison[{WORKLOAD}-{label}]']
            encoded = require_object(sample, 'fixture.sample')
            encoded['median'] = value
            encoded['mean'] = value

    assert f'| Direct overhead | {expected} |' in render(dataset, calibration, BUDGETS)
