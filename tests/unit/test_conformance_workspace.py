import os
from pathlib import Path, PureWindowsPath

import pytest

from scripts.conformance import workspace


def test_configuration_path_uses_toml_and_json_safe_separators() -> None:
    windows_path = PureWindowsPath(r'C:\Users\runneradmin\AppData\Local\Temp\venvs\core')

    assert workspace.configuration_path(windows_path) == 'C:/Users/runneradmin/AppData/Local/Temp/venvs/core'


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
