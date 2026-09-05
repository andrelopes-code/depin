"""The accepted dataset committed in the repository, and what a later run reads back from it.

One dataset is published at a time; history lives in git. It is the evidence the
results page renders, and it is also an input to the next measurement: a workload's
sampling floor is derived from the cost this dataset already recorded for it, so a
rule stated in seconds does not have to be guessed at in rounds.

Reading it back is safe against the obvious circularity. The floor changes how many
rounds a repetition runs; it does not change what one round costs, which is the only
figure taken from here.
"""

import statistics
from pathlib import Path

from benchmarks.harness import HarnessError, read_json, reduce, require_object

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'benchmarks' / 'results'
PUBLISHED_SIDE = 'head'


def accepted() -> Path:
    """The one dataset directory under `benchmarks/results`.

    Raises:
        HarnessError: the results directory is missing, or holds anything other
            than exactly one dataset. Two would leave the published page ambiguous
            about which one it renders.
    """
    if not RESULTS.is_dir():
        raise HarnessError(f'{RESULTS}: no published results directory')
    datasets = sorted(
        path
        for path in RESULTS.iterdir()
        if path.is_dir() and (path / 'environment.json').is_file() and any(path.glob('rep*.json'))
    )
    if len(datasets) != 1:
        raise HarnessError(
            f'{RESULTS}: holds {len(datasets)} datasets ({", ".join(path.name for path in datasets)}); '
            'exactly one is published at a time, and history lives in git'
        )
    return datasets[0]


def aggregates(dataset: Path) -> dict[str, list[reduce.Aggregate]]:
    """Every repetition of every workload in `dataset`, keyed by the name it was measured under.

    A paired collection is read from its published side; a single-revision
    collection holds its repetitions directly.

    Raises:
        HarnessError: the directory carries no repetition file, or one of them is
            malformed.
    """
    side = dataset / PUBLISHED_SIDE if (dataset / PUBLISHED_SIDE).is_dir() else dataset
    files = sorted(side.glob('rep*.json'))
    if not files:
        raise HarnessError(f'{side}: carries no rep<index>.json; the dataset measured nothing')
    measured: dict[str, list[reduce.Aggregate]] = {}
    for path in files:
        payload = read_json(path)
        stored = require_object(payload.get('aggregates'), f'{path}: aggregates')
        for name, aggregate in reduce.decode_all(stored, str(path)).items():
            measured.setdefault(name, []).append(aggregate)
    return measured


def costs() -> dict[str, float]:
    """Seconds per round for every workload the accepted dataset measured.

    The median across repetitions, which is the same summary the published page
    prints, so a floor derived here is derived from the number a reader can see.
    Returns an empty mapping when no dataset is published yet, because a tree
    without one still has to be measurable.
    """
    try:
        dataset = accepted()
    except HarnessError:
        return {}
    return {
        name: statistics.median([aggregate.median for aggregate in repetitions])
        for name, repetitions in aggregates(dataset).items()
    }
