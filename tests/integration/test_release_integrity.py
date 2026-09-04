from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_ci_calls_the_shared_release_verification_workflow() -> None:
    ci = (ROOT / '.github/workflows/ci.yml').read_text()

    assert 'uses: ./.github/workflows/release-verification.yml' in ci
    assert 'ref: ${{ github.sha }}' in ci


def test_release_publish_depends_on_verification_of_the_release_tag() -> None:
    release = (ROOT / '.github/workflows/release.yml').read_text()

    assert 'verify-release:' in release
    assert 'uses: ./.github/workflows/release-verification.yml' in release
    assert 'ref: ${{ needs.release-please.outputs.tag_name }}' in release
    assert 'needs: [release-please, verify-release]' in release


def test_shared_release_verification_includes_repository_and_documentation_gates() -> None:
    verification = (ROOT / '.github/workflows/release-verification.yml').read_text()

    assert 'uv sync --locked --all-extras --group docs' in verification
    assert 'uv run ruff format --check' in verification
    assert 'uv run ruff check' in verification
    assert 'uv run basedpyright' in verification
    assert 'uv run mypy' in verification
    assert 'uv run coverage run -m pytest' in verification
    assert 'uv run --group docs mkdocs build --strict' in verification
