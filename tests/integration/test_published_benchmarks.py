import os
import shutil
import subprocess
import sys
from pathlib import Path

from test_harness_reports import write

from benchmarks import test_latency
from benchmarks.contracts import Metric, Tier
from benchmarks.harness import budgets as budget_module
from benchmarks.harness import environment, pairs, reduce, report, unmeasured
from benchmarks.workloads import WORKLOADS

ROOT = Path(__file__).resolve().parents[2]
SEED = 20260902


def test_a_case_the_published_dataset_does_not_cover_falls_back_to_the_round_count() -> None:
    """A workload added since the dataset was published still has to be measurable."""
    assert test_latency.floor('a_workload_no_dataset_has_ever_carried-depin') == reduce.MINIMUM_ROUNDS


def test_a_published_case_takes_its_floor_from_the_cost_the_dataset_recorded() -> None:
    published = dict(sorted(test_latency._PUBLISHED.items()))  # pyright: ignore[reportPrivateUsage]

    assert published, 'the accepted dataset carries no latency case to derive a floor from'
    for case, median in published.items():
        assert test_latency.floor(case) == reduce.rounds_for(median)


def test_the_published_page_separates_the_application_tier_and_gives_it_quantiles(tmp_path: Path) -> None:
    dataset = tmp_path / 'dataset'
    write(dataset / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 1, 'seed': SEED})
    write(
        dataset / 'rep0.json',
        {
            'repetition': 0,
            'first': 'head',
            'aggregates': {
                'test_latency[an_endpoint-depin]': {
                    'rounds': 1000,
                    'minimum': 1e-3,
                    'median': 1e-3,
                    'mean': 1e-3,
                    'stddev': 0.0,
                    'iqr': 0.0,
                    'p95': 2e-3,
                    'p99': 3e-3,
                    'cpu': 900000.0,
                    'tier': Tier.APPLICATION.value,
                },
                'test_latency[a_lookup-depin]': {
                    'rounds': 1000,
                    'minimum': 1e-6,
                    'median': 1e-6,
                    'mean': 1e-6,
                    'stddev': 0.0,
                    'iqr': 0.0,
                    'p95': 2e-6,
                    'p99': 3e-6,
                    'tier': Tier.ISOLATED.value,
                },
            },
        },
    )

    rendered = report.render(dataset)
    latency, application = rendered.split('## Application tier')

    assert 'a_lookup' in latency
    assert 'an_endpoint' not in latency
    assert 'an_endpoint' in application
    assert '3.000 ms' in application
    assert '900.000 µs' in application


def test_the_published_page_states_every_retired_and_refused_measurement(tmp_path: Path) -> None:
    write(tmp_path / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 1, 'seed': SEED})

    rendered = report.render(tmp_path)

    for retirement in unmeasured.RETIRED:
        assert retirement.workload in rendered
        assert retirement.covered_by in rendered
    for refusal in unmeasured.REFUSED:
        assert refusal.case in rendered
        assert refusal.needed in rendered


def test_no_retired_workload_is_still_in_the_inventory() -> None:
    """Retirement is a decision, and a decision that the tree quietly reverses is not one."""
    declared = {workload.name for workload in WORKLOADS} | {
        pairs.split_size(workload.name)[0] for workload in WORKLOADS if workload.claim.metric is Metric.SCALING
    }

    for retirement in unmeasured.RETIRED:
        assert retirement.workload not in declared


def test_no_retired_workload_still_carries_a_budget() -> None:
    available = budget_module.load(ROOT / 'benchmarks' / 'budgets.toml')
    retired = {retirement.workload for retirement in unmeasured.RETIRED}

    assert not {workload for workload, _ in available} & retired


def test_competitive_cached_lookup_seed_applies_only_to_the_cached_resolution_path(tmp_path: Path) -> None:
    patch = ROOT / 'benchmarks' / 'seeds' / 'competitive-cached-lookup.patch'
    seeded_package = tmp_path / 'depin'
    shutil.copytree(ROOT / 'depin', seeded_package)
    initialized = subprocess.run(
        ('git', 'init', '--quiet', str(tmp_path)), cwd=ROOT, capture_output=True, text=True, check=False
    )

    applied = subprocess.run(
        ('git', 'apply', str(patch)),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert initialized.returncode == 0, initialized.stderr
    assert applied.returncode == 0, applied.stderr
    observed = subprocess.run(
        (
            sys.executable,
            '-c',
            """
from depin import Container, Scope
from depin._core.frozen import FrozenContainer


class Cached: pass


class Transient: pass


container = Container().bind(Cached).bind(Transient, scope=Scope.TRANSIENT).freeze()
assert '_warm_cached_lookup_probe' in FrozenContainer.__slots__
assert container._warm_cached_lookup_probe == {}

container.resolve(Transient)
container.resolve(Transient)
assert container._warm_cached_lookup_probe == {}

cached = container.resolve(Cached)
assert container._warm_cached_lookup_probe == {}
assert container.resolve(Cached) is cached
assert len(container._warm_cached_lookup_probe) == 1
""",
        ),
        cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert observed.returncode == 0, observed.stderr
