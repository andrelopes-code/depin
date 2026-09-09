import os
from pathlib import Path

import pytest

from scripts.conformance import workspace


@pytest.mark.parametrize(
    ('platform', 'directory', 'executable'),
    [('posix', 'bin', 'python'), ('nt', 'Scripts', 'python.exe')],
)
def test_venv_python_uses_platform_executable_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    platform: str,
    directory: str,
    executable: str,
) -> None:
    venv = tmp_path / 'venv'
    monkeypatch.setattr(os, 'name', platform)

    assert workspace.venv_python(venv) == venv / directory / executable
