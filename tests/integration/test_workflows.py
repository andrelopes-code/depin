import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from benchmarks.comparison import protocol

WORKFLOW = Path('.github/workflows/competitive-benchmarks.yml')


def _workflow_step(name: str) -> str:
    lines = WORKFLOW.read_text(encoding='utf-8').splitlines()
    name_line = f'      - name: {name}'
    start = lines.index(name_line)
    run = lines.index('        run: |', start) + 1
    end = next((index for index in range(run, len(lines)) if lines[index].startswith('      - name: ')), len(lines))
    return textwrap.dedent('\n'.join(lines[run:end]))


def test_github_workflows_are_accepted_by_the_actions_parser() -> None:
    workflows = tuple(sorted(Path('.github/workflows').glob('*.yml')))
    result = subprocess.run(
        ('actionlint', '-shellcheck=', '-pyflakes=', *(str(path) for path in workflows)),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name == 'nt', reason='the competitive workflow runs on Ubuntu')
def test_competitive_workflow_materializes_an_exact_archive_with_the_runner_umask(tmp_path: Path) -> None:
    revision = subprocess.run(
        ('git', 'rev-parse', 'HEAD'),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    baseline = tmp_path / 'baseline'
    environment = os.environ | {
        'BASELINE_DIR': str(baseline),
        'BASELINE_REVISION': revision,
    }

    result = subprocess.run(
        ('bash', '-c', f'umask 0022\n{_workflow_step("Materialize the baseline revision")}'),
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert protocol.baseline_preflight(baseline, revision) == revision
