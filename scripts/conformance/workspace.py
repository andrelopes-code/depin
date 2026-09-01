"""The wheel, the three interpreters, the copied corpus, and every subprocess."""

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from string import Template
from typing import Final

from scripts.conformance.model import CHECKOUT, CONFORMANCE, ConformanceError, Pins, Workspace

LEAKING_VARIABLES: Final = (
    'VIRTUAL_ENV',
    'PYTHONPATH',
    'PYTHONHOME',
    'MYPYPATH',
    'CONDA_PREFIX',
    'TY_CONFIG_FILE',
    'PYREFLY_CONFIG',
)


def subprocess_environment(root: Path) -> dict[str, str]:
    """The environment every checker subprocess runs under.

    ``VIRTUAL_ENV`` is the dangerous one: `uv run` sets it to the checkout's own
    interpreter, and both ty and Pyrefly read it when no interpreter is named.
    """
    environment = dict(os.environ)
    for leak in LEAKING_VARIABLES:
        environment.pop(leak, None)
    empty = root / 'xdg-config'
    empty.mkdir(exist_ok=True)
    environment['XDG_CONFIG_HOME'] = str(empty)
    environment['NO_COLOR'] = '1'
    return environment


def run_outside_checkout(
    command: Sequence[str], cwd: Path, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess, having proven first that it cannot see the checkout."""
    working = cwd.resolve()
    if working == CHECKOUT or CHECKOUT in working.parents:
        raise ConformanceError(
            f'refusing to check from {working}: the checkout {CHECKOUT} is that directory or an ancestor of it, '
            'so a checker would resolve depin out of the source tree and report success against an empty interpreter'
        )
    return subprocess.run(
        list(command), cwd=working, env=dict(environment), capture_output=True, text=True, check=False
    )


def run_in_checkout(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=CHECKOUT, capture_output=True, text=True, check=False)


def venv_python(venv: Path) -> Path:
    return venv / ('Scripts' if os.name == 'nt' else 'bin') / 'python'


def require_wheel(supplied: Path) -> Path:
    if supplied.suffix != '.whl' or not supplied.is_file():
        raise ConformanceError(f'--wheel must name an existing .whl file, got {supplied}')
    return supplied.resolve()


def resolve_wheel(root: Path, supplied: Path | None) -> Path:
    """Use the wheel CI already built and uploaded, or build one for a local run."""
    if supplied is not None:
        return require_wheel(supplied)
    distributions = root / 'dist'
    built = run_in_checkout(['uv', 'build', '--wheel', '--out-dir', str(distributions)])
    if built.returncode != 0:
        raise ConformanceError(f'uv build failed:\n{built.stdout}{built.stderr}')
    wheels = sorted(distributions.glob('*.whl'))
    if len(wheels) != 1:
        raise ConformanceError(f'expected exactly one wheel in {distributions}, found {len(wheels)}')
    return wheels[0]


def build_workspace(root: Path, pins: Pins, wheel: Path) -> Workspace:
    shutil.copytree(CONFORMANCE, root / 'conformance')

    venvs: dict[str, Path] = {}
    for name in ('core', 'extras', 'empty'):
        venv = root / 'venvs' / name
        created = run_in_checkout(['uv', 'venv', '--python', pins.python, str(venv)])
        if created.returncode != 0:
            raise ConformanceError(f'uv venv {name} failed:\n{created.stdout}{created.stderr}')
        venvs[name] = venv

    # `uv pip install "<wheel>[extra]"` is a parse error; the `name[extras] @ <url>` form is required.
    requirements = {
        'core': f'pydepin @ {wheel.as_uri()}',
        'extras': f'pydepin[{",".join(pins.extras)}] @ {wheel.as_uri()}',
    }
    for name, requirement in requirements.items():
        target = str(venv_python(venvs[name]))
        installed = run_in_checkout(['uv', 'pip', 'install', '--python', target, requirement])
        if installed.returncode != 0:
            raise ConformanceError(
                f'installing into the {name} interpreter failed:\n{installed.stdout}{installed.stderr}'
            )
    return Workspace(root=root, corpus=root / 'conformance', wheel=wheel, venvs=venvs)


def render_configs(workspace: Workspace) -> None:
    """Write one rendered configuration per checker per interpreter.

    Stock Pyright takes ``venvPath`` plus ``venv``; ``pythonPath`` is not a
    recognised key and is ignored with a warning, so the template carries the
    venv's parent and its name separately.
    """
    directory = workspace.corpus / 'config'
    # A rendered file is named `<stem>.<mode><suffix>`, so a dotted stem marks
    # an output rather than a template and re-rendering one would compound.
    templates = sorted(
        path for path in directory.glob('*') if path.suffix in ('.json', '.toml', '.ini') and '.' not in path.stem
    )
    for mode, venv in workspace.venvs.items():
        substitutions = {
            'venv': str(venv),
            'venv_parent': str(venv.parent),
            'venv_name': venv.name,
            'python': str(venv_python(venv)),
        }
        for template in templates:
            rendered = Template(template.read_text(encoding='utf-8')).substitute(substitutions)
            template.with_name(f'{template.stem}.{mode}{template.suffix}').write_text(rendered, encoding='utf-8')
