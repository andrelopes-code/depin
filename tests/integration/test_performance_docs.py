"""The published results page is generated, and these are what make that true.

A number on the site cannot have been typed by hand: the page is asserted to be
the render of the dataset committed beside it. The freshness rule follows from
the same assertion — a workload added, renamed or removed leaves the dataset
incomplete, and this fails until the dataset is refreshed.
"""

from pathlib import Path

import pytest

from benchmarks.contracts import Metric, Workload
from benchmarks.harness import published
from benchmarks.harness.pairs import split_size
from benchmarks.harness.report import render
from benchmarks.workloads import WORKLOADS

PAGE = Path(__file__).resolve().parents[2] / 'docs' / 'performance' / 'results.md'


def test_one_dataset_is_accepted() -> None:
    """Exactly one, because the page renders one and history lives in git."""
    assert published.accepted().is_dir()


def test_the_page_is_the_render_of_the_accepted_dataset() -> None:
    assert PAGE.read_text(encoding='utf-8') == render(published.accepted())


def _published_name(workload: Workload) -> str:
    """The name a workload is published and gated under.

    A scaling workload is one point on a curve, and the curve is what carries a
    verdict, so the size suffix does not appear on its own.
    """
    if workload.claim.metric is Metric.SCALING:
        return split_size(workload.name)[0]
    return workload.name


@pytest.mark.parametrize('workload', WORKLOADS, ids=[workload.name for workload in WORKLOADS])
def test_every_workload_appears_in_the_published_dataset(workload: Workload) -> None:
    """A workload the inventory declares and the dataset does not cover is an unmeasured claim."""
    assert _published_name(workload) in PAGE.read_text(encoding='utf-8'), (
        f'{workload.name} is declared but absent from the published results. '
        'Refresh the dataset rather than removing the workload.'
    )
