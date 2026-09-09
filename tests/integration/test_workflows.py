import subprocess
from pathlib import Path


def test_github_workflows_are_accepted_by_the_actions_parser() -> None:
    workflows = tuple(sorted(Path('.github/workflows').glob('*.yml')))
    result = subprocess.run(
        ('actionlint', '-shellcheck=', '-pyflakes=', *(str(path) for path in workflows)),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
