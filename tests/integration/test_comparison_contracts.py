import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import benchmarks.comparison as comparison
from benchmarks.comparison import WORKLOADS as COMPARATIVE_WORKLOADS
from benchmarks.comparison import inventory
from benchmarks.comparison.adapters import ADAPTERS
from benchmarks.comparison.contracts import (
    AbsoluteTarget,
    Candidate,
    Competitor,
    Equivalence,
)
from benchmarks.comparison.targets import load
from benchmarks.contracts import Implementation, Metric, Observation, Prepared, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads import WORKLOADS


def test_competitive_workflow_is_locked_and_collects_separate_null_and_real_evidence() -> None:
    workflow = Path('.github/workflows/competitive-benchmarks.yml').read_text(encoding='utf-8')

    assert 'workflow_dispatch:' in workflow
    assert 'pull_request:\n    types: [labeled]' in workflow
    assert "github.event.label.name == 'competitive-benchmark'" in workflow
    assert (
        "if: github.event_name == 'workflow_dispatch' || github.event.label.name == 'competitive-benchmark'" in workflow
    )
    assert 'contents: read' in workflow
    assert 'timeout-minutes: 120' in workflow
    assert "python-version: '3.12'" in workflow
    assert 'uv sync --locked --no-default-groups --group bench' in workflow
    assert 'pytest benchmarks/test_comparison.py -q' in workflow
    assert 'comparison collect --null' in workflow
    assert 'comparison collect' in workflow
    assert '--baseline-dir' in workflow
    assert '--budgets benchmarks/budgets.toml' in workflow
    assert 'leadership calibrate' in workflow
    assert 'leadership evaluate' in workflow
    assert 'comparison_report' in workflow
    assert '- name: Render Markdown summary\n        if: always()' in workflow
    assert 'actions/upload-artifact@65c4c4a1ddee5b72f698fdd19549f0f0fb45cf08' in workflow
    assert 'if: always()' in workflow
    assert 'git archive' in workflow
    assert 'baseline-revision' in workflow
    assert '--baseline-revision "$BASELINE_REVISION"' in workflow
    assert '- name: Prepare artifact placeholders' in workflow
    assert workflow.index('- name: Prepare artifact placeholders') < workflow.index(
        '- name: Install the locked benchmark environment'
    )
    assert 'if-no-files-found: error' in workflow
    assert 'if-no-files-found: ignore' not in workflow
    assert '${{ runner.temp }}/competitive-benchmark-artifacts' in workflow
    assert '"$ARTIFACT_DIR/null"' in workflow
    assert '"$ARTIFACT_DIR/real"' in workflow
    assert '"$ARTIFACT_DIR/calibration.json"' in workflow
    assert '"$ARTIFACT_DIR/competitive-benchmarks.md"' in workflow
    assert '"$ARTIFACT_DIR/status.txt"' in workflow
    assert workflow.index('- name: Install the locked benchmark environment') < workflow.index(
        '- name: Observe adapter equivalence before collection'
    )
    assert workflow.index('- name: Observe adapter equivalence before collection') < workflow.index(
        '- name: Collect null evidence'
    )
    assert workflow.index('- name: Collect null evidence') < workflow.index('- name: Collect competitive evidence')
    assert 'requirements' not in workflow
    uses = [line.split('#', 1)[0].rstrip() for line in workflow.splitlines() if 'uses:' in line]
    assert uses
    assert all(re.fullmatch(r'\s*(?:- )?uses: \S+@[0-9a-f]{40}', line) for line in uses)
    assert '\n  push:' not in workflow


def test_source_checking_syncs_the_locked_benchmark_group() -> None:
    workflow = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')

    assert 'uv sync --locked --all-extras --group bench' in workflow


def _workflow_step(workflow: str, name: str) -> str:
    marker = f'      - name: {name}\n'
    start = workflow.index(marker)
    end = workflow.find('\n      - name: ', start + len(marker))
    return workflow[start:] if end < 0 else workflow[start:end]


def test_competitive_workflow_bounds_collection_timeouts_and_keeps_step_arguments_isolated() -> None:
    workflow = Path('.github/workflows/competitive-benchmarks.yml').read_text(encoding='utf-8')
    null = _workflow_step(workflow, 'Collect null evidence')
    real = _workflow_step(workflow, 'Collect competitive evidence')
    upload = _workflow_step(workflow, 'Upload competitive benchmark evidence')
    summary = _workflow_step(workflow, 'Render Markdown summary')

    assert '--null' in null
    assert '--timeout-seconds 1500' in null
    assert '--null' not in real
    assert '--timeout-seconds 4500' in real
    assert 1500 + 4500 <= 6000
    assert 'if: always()' in upload
    assert 'if-no-files-found: error' in upload
    assert 'if: always()' in summary


def test_documented_competitive_baseline_is_a_full_sha_used_by_archive_and_collections() -> None:
    contributing = Path('CONTRIBUTING.md').read_text(encoding='utf-8')
    match = re.search(r'^BASELINE_REVISION=([0-9a-f]+)$', contributing, flags=re.MULTILINE)

    assert match is not None
    revision = match.group(1)
    assert re.fullmatch(r'[0-9a-f]{40}', revision)
    assert 'git archive "$BASELINE_REVISION"' in contributing
    assert contributing.count('--baseline-revision "$BASELINE_REVISION"') == 2


def _implementation() -> Implementation:
    return Implementation(
        label='candidate-1.0',
        prepare=lambda: Prepared(call=object),
        observe=lambda: Observation(result='object', constructed=(), closed=()),
    )


@pytest.mark.parametrize('equivalence', [Equivalence.EQUIVALENT, Equivalence.PARTIAL])
def test_a_timed_candidate_requires_an_implementation(equivalence: Equivalence) -> None:
    with pytest.raises(HarnessError, match='requires an implementation'):
        Candidate('workload', Competitor('candidate', '1.0'), equivalence, 'stated difference', None)


def test_an_incomparable_candidate_cannot_carry_an_implementation() -> None:
    with pytest.raises(HarnessError, match='must not carry an implementation'):
        Candidate(
            'workload',
            Competitor('candidate', '1.0'),
            Equivalence.INCOMPARABLE,
            'different lifecycle',
            _implementation(),
        )


@pytest.mark.parametrize('reason', ['', ' padded', 'padded '])
def test_a_candidate_reason_is_non_empty_and_unpadded(reason: str) -> None:
    with pytest.raises(HarnessError, match='reason'):
        Candidate('workload', Competitor('candidate', '1.0'), Equivalence.PARTIAL, reason, _implementation())


@pytest.mark.parametrize('workload', ['not-valid', 'NotValid'])
def test_a_candidate_workload_must_be_a_lower_case_identifier(workload: str) -> None:
    with pytest.raises(HarnessError, match='workload'):
        Candidate(workload, Competitor('candidate', '1.0'), Equivalence.PARTIAL, 'stated difference', _implementation())


def test_a_candidate_implementation_label_must_match_the_competitor() -> None:
    implementation = Implementation(
        label='other-2.0',
        prepare=lambda: Prepared(call=object),
        observe=lambda: Observation(result='object', constructed=(), closed=()),
    )
    with pytest.raises(HarnessError, match='implementation label'):
        Candidate('workload', Competitor('candidate', '1.0'), Equivalence.PARTIAL, 'stated difference', implementation)


@pytest.mark.parametrize('fraction', [0.0, -0.1, 1.1])
def test_an_absolute_target_fraction_must_be_within_bounds(fraction: float) -> None:
    with pytest.raises(HarnessError, match='direct fraction'):
        AbsoluteTarget(12e-6, fraction, 'handler budget')


@pytest.mark.parametrize('fixed_seconds', [0.0, -1.0])
def test_an_absolute_target_fixed_seconds_must_be_positive(fixed_seconds: float) -> None:
    with pytest.raises(HarnessError, match='fixed target'):
        AbsoluteTarget(fixed_seconds, 0.1, 'handler budget')


@pytest.mark.parametrize('fixed_seconds', [math.nan, math.inf, -math.inf])
def test_an_absolute_target_fixed_seconds_must_be_finite(fixed_seconds: float) -> None:
    with pytest.raises(HarnessError, match='fixed target'):
        AbsoluteTarget(fixed_seconds, 0.1, 'handler budget')


@pytest.mark.parametrize('justification', ['', ' padded', 'padded '])
def test_an_absolute_target_justification_is_non_empty_and_unpadded(justification: str) -> None:
    with pytest.raises(HarnessError, match='justification'):
        AbsoluteTarget(12e-6, 0.1, justification)


@pytest.mark.parametrize(('direct_seconds', 'expected'), [(80e-6, 8e-6), (240e-6, 12e-6)])
def test_an_absolute_target_uses_the_lower_applicable_ceiling(direct_seconds: float, expected: float) -> None:
    target = AbsoluteTarget(12e-6, 0.1, 'handler budget')
    assert target.ceiling(direct_seconds) == pytest.approx(expected)


def test_every_direct_latency_workload_has_one_absolute_target() -> None:
    targets = load(Path('benchmarks/leadership-targets.toml'))
    expected = {
        workload.name
        for workload in WORKLOADS
        if workload.claim.metric is Metric.LATENCY and workload.baseline is not None
    }
    assert set(targets) == expected


def test_an_unknown_target_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / 'targets.toml'
    path.write_text(
        '[case]\nfixed_seconds = 0.1\njustification = "reason"\nunknown = 1\n',
        encoding='utf-8',
    )
    with pytest.raises(HarnessError, match='unknown field'):
        load(path)


def test_invalid_utf8_target_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / 'targets.toml'
    path.write_bytes(b'[case]\njustification = "\xff"\n')
    with pytest.raises(HarnessError, match=f'{path}.*invalid start byte'):
        load(path)


@pytest.mark.parametrize(
    'contents',
    [
        '[case\nfixed_seconds = 0.1\njustification = "reason"\n',
        '[case]\nfixed_seconds = 0.1\nfixed_seconds = 0.2\njustification = "reason"\n',
        '[case]\nfixed_seconds = 0.1\njustification = "reason"\n[case]\n',
    ],
)
def test_malformed_or_duplicate_target_toml_is_rejected(tmp_path: Path, contents: str) -> None:
    path = tmp_path / 'targets.toml'
    path.write_text(contents, encoding='utf-8')
    with pytest.raises(HarnessError, match=f'{path}.*cannot load targets'):
        load(path)


def test_an_unreadable_target_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match=f'{tmp_path}.*cannot load targets'):
        load(tmp_path)


@pytest.mark.parametrize(
    ('field', 'value'),
    [('fixed_seconds', '"not-a-number"'), ('fraction_of_direct', '"not-a-number"'), ('justification', '1')],
)
def test_target_fields_use_strict_narrowing_helpers(tmp_path: Path, field: str, value: str) -> None:
    path = tmp_path / 'targets.toml'
    fixed = value if field == 'fixed_seconds' else '0.1'
    fraction = f'fraction_of_direct = {value}\n' if field == 'fraction_of_direct' else ''
    justification = value if field == 'justification' else '"reason"'
    path.write_text(
        f'[case]\nfixed_seconds = {fixed}\n{fraction}justification = {justification}\n',
        encoding='utf-8',
    )
    with pytest.raises(HarnessError, match=f'case.{field}'):
        load(path)


def test_fraction_of_direct_is_materialized() -> None:
    target = load(Path('benchmarks/leadership-targets.toml'))['fastapi_cpu_light_endpoint']
    assert target.fraction_of_direct == 0.1


def test_authored_targets_match_the_versioned_oracle() -> None:
    expected = {
        'resolve_cached_singleton': 0.0000005,
        'resolve_cached_singleton_through_an_alias': 0.000001,
        'resolve_singleton_through_a_two_deep_decoration_chain': 0.0000015,
        'resolve_a_collection_of_10': 0.000005,
        'resolve_a_collection_of_100': 0.00005,
        'resolve_a_transient_chain': 0.00001,
        'open_and_close_a_scope': 0.000012,
        'call_through_an_inject_wrapper': 0.000001,
        'call_through_an_inject_wrapper_with_explicit_arguments': 0.000001,
        'resolve_an_async_singleton': 0.0000005,
        'resolve_with_no_active_override': 0.0000005,
        'resolve_through_an_active_override': 0.000001,
        'resolve_a_generic_key': 0.0000005,
        'construct_a_singleton_for_the_first_time': 0.0000005,
        'resolve_a_sync_resource_with_teardown': 0.000003,
        'warmup_a_cold_singleton_graph': 0.0005,
        'open_a_request_shaped_scope': 0.0000035,
        'fastapi_cpu_light_endpoint': 0.000012,
        'fastapi_request_scoped_graph': 0.000016,
        'fastapi_singletons_and_transients': 0.000016,
        'fastapi_async_resource_teardown': 0.000018,
        'fastapi_endpoint_with_work': 0.000012,
        'fastapi_application_startup': 0.00003,
    }
    targets = load(Path('benchmarks/leadership-targets.toml'))
    assert {name: target.fixed_seconds for name, target in targets.items()} == expected
    assert {name: target.fraction_of_direct for name, target in targets.items() if name.startswith('fastapi_')} == {
        'fastapi_cpu_light_endpoint': 0.1,
        'fastapi_request_scoped_graph': 0.1,
        'fastapi_singletons_and_transients': 0.1,
        'fastapi_async_resource_teardown': 0.1,
        'fastapi_endpoint_with_work': 0.1,
        'fastapi_application_startup': 0.1,
    }
    assert all(
        target.justification and target.justification.strip() == target.justification for target in targets.values()
    )
    assert all('formula' in target.justification for target in targets.values())


def test_a_non_positive_target_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / 'targets.toml'
    path.write_text('[case]\nfixed_seconds = 0\njustification = "reason"\n', encoding='utf-8')
    with pytest.raises(HarnessError, match='fixed target'):
        load(path)


def test_comparative_inventory_covers_every_workload_in_adapter_order() -> None:
    expected_targets = {
        workload.name
        for workload in WORKLOADS
        if workload.claim.metric is Metric.LATENCY and workload.baseline is not None
    }

    assert tuple(comparative.workload for comparative in COMPARATIVE_WORKLOADS) == WORKLOADS
    assert all(len(comparative.candidates) == len(ADAPTERS) for comparative in COMPARATIVE_WORKLOADS)
    assert all(
        tuple(candidate.competitor for candidate in comparative.candidates)
        == tuple(adapter.competitor for adapter in ADAPTERS)
        for comparative in COMPARATIVE_WORKLOADS
    )
    assert all(
        len(
            {
                candidate.implementation.label
                for candidate in comparative.candidates
                if candidate.implementation is not None
            }
        )
        == len([candidate for candidate in comparative.candidates if candidate.implementation is not None])
        for comparative in COMPARATIVE_WORKLOADS
    )
    assert all(
        candidate.implementation is None
        or candidate.equivalence is not Equivalence.EQUIVALENT
        or candidate.implementation.observe() == comparative.workload.subject.observe()
        for comparative in COMPARATIVE_WORKLOADS
        for candidate in comparative.candidates
    )
    assert {
        comparative.workload.name for comparative in COMPARATIVE_WORKLOADS if comparative.target is not None
    } == expected_targets


def test_comparison_namespace_exports_only_the_workload_inventory() -> None:
    namespace: dict[str, object] = {}
    exec('from benchmarks.comparison import *', namespace)

    assert not hasattr(comparison, 'build')
    assert comparison.__all__ == ('WORKLOADS',)
    assert {name for name in namespace if name != '__builtins__'} == {'WORKLOADS'}
    assert namespace['WORKLOADS'] is COMPARATIVE_WORKLOADS


@dataclass(frozen=True, slots=True)
class _MismatchedCompetitorAdapter:
    competitor: Competitor = field(default_factory=lambda: Competitor('expected-adapter', '1.0'))

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]:
        return (
            Candidate(
                workloads[0].name,
                Competitor('wrong-record', '1.0'),
                Equivalence.INCOMPARABLE,
                'the controlled record belongs to a different competitor',
                None,
            ),
        )


def test_inventory_rejects_a_candidate_from_a_different_competitor() -> None:
    workload = WORKLOADS[0]

    with pytest.raises(
        HarnessError,
        match=(rf'{workload.name}.*wrong-record-1\.0.*expected-adapter-1\.0.*return a candidate for the adapter'),
    ):
        _ = inventory.index_candidates(_MismatchedCompetitorAdapter(), (workload,))
