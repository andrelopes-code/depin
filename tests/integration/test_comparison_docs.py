import json
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError
from benchmarks.harness.comparison_report import main, render

FIXTURE = Path(__file__).parents[1] / 'fixtures' / 'comparison'
BUDGETS = Path('benchmarks/budgets.toml')


def _evidence() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads((FIXTURE / 'accepted.json').read_text(encoding='utf-8')),
        json.loads((FIXTURE / 'calibration.json').read_text(encoding='utf-8')),
    )


def test_comparison_report_renders_evidence_without_aggregate_ranking() -> None:
    dataset, calibration = _evidence()

    rendered = render(dataset, calibration, BUDGETS)

    for expected in (
        'allocations_of_a_cached_singleton_resolution',
        'Claim',
        'A cached singleton resolution allocates no additional Python objects.',
        'same observed cached resolution',
        'does not preserve the complete observation',
        'cannot express this cache lifecycle',
        '900.000 ms',
        '[-10.00%, -10.00%]',
        '1.0%',
        '+0.500 s',
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
