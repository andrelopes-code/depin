import io
import subprocess
import tarfile
from pathlib import Path

import pytest

import benchmarks.comparison.collection as comparison
from benchmarks.comparison import protocol
from benchmarks.harness import HarnessError

EXPECTED_IDS = {'resolve-depin', 'resolve-wireup-2.12.0'}
BUDGETS = Path('benchmarks/budgets.toml')
BASELINE_REVISION = 'a' * 40
REAL_DETERMINISTIC = comparison.collect_deterministic
REAL_BASELINE_VALIDATION = protocol.validate_baseline_archive


def _expected_file(revision: str) -> dict[str, tuple[str, int, bytes]]:
    _ = revision
    return {'expected.py': ('file', 0o644, b'expected\n')}


def _no_expected_entries(revision: str) -> dict[str, tuple[str, int, bytes]]:
    _ = revision
    return {}


def _expected_symlink(revision: str) -> dict[str, tuple[str, int, bytes]]:
    _ = revision
    return {'link': ('symlink', 0o777, b'expected-target')}


def _expected_mode(revision: str) -> dict[str, tuple[str, int, bytes]]:
    _ = revision
    return {'mode.py': ('file', 0o644, b'content\n')}


def test_baseline_preflight_rejects_marker_matched_but_wrong_archive_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    (baseline / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    (baseline / 'wrong.py').write_text('wrong\n', encoding='utf-8')
    monkeypatch.setattr(protocol, 'validate_baseline_archive', REAL_BASELINE_VALIDATION)
    monkeypatch.setattr(protocol, 'archive_entries', _expected_file)

    with pytest.raises(HarnessError, match='baseline archive'):
        _ = protocol.baseline_preflight(baseline, BASELINE_REVISION)


def test_baseline_preflight_rejects_an_extra_file_even_with_a_matched_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    (baseline / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    (baseline / 'extra.py').write_text('extra\n', encoding='utf-8')
    monkeypatch.setattr(protocol, 'validate_baseline_archive', REAL_BASELINE_VALIDATION)
    monkeypatch.setattr(protocol, 'archive_entries', _no_expected_entries)

    with pytest.raises(HarnessError, match='baseline archive'):
        _ = protocol.baseline_preflight(baseline, BASELINE_REVISION)


def test_baseline_preflight_rejects_a_symlink_with_the_wrong_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    (baseline / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    (baseline / 'link').symlink_to('actual-target')
    monkeypatch.setattr(protocol, 'validate_baseline_archive', REAL_BASELINE_VALIDATION)
    monkeypatch.setattr(protocol, 'archive_entries', _expected_symlink)

    with pytest.raises(HarnessError, match='baseline archive'):
        _ = protocol.baseline_preflight(baseline, BASELINE_REVISION)


def test_baseline_preflight_rejects_a_file_with_the_wrong_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    (baseline / '.depin-baseline-revision').write_text(f'{BASELINE_REVISION}\n', encoding='utf-8')
    executable = baseline / 'mode.py'
    executable.write_text('content\n', encoding='utf-8')
    executable.chmod(0o755)
    monkeypatch.setattr(protocol, 'validate_baseline_archive', REAL_BASELINE_VALIDATION)
    monkeypatch.setattr(protocol, 'archive_entries', _expected_mode)

    with pytest.raises(HarnessError, match='baseline archive'):
        _ = protocol.baseline_preflight(baseline, BASELINE_REVISION)


def test_baseline_preflight_accepts_a_real_git_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    revision = subprocess.run(('git', 'rev-parse', 'HEAD'), capture_output=True, text=True, check=True).stdout.strip()
    archive = subprocess.run(('git', 'archive', '--format=tar', revision), capture_output=True, check=True).stdout
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as stream:
        stream.extractall(baseline, filter='fully_trusted')
    (baseline / '.depin-baseline-revision').write_text(f'{revision}\n', encoding='utf-8')
    monkeypatch.setattr(protocol, 'validate_baseline_archive', REAL_BASELINE_VALIDATION)

    assert protocol.baseline_preflight(baseline, revision) == revision
