"""Absolute links to the documentation site must carry the version alias.

The site is published with `mike`, so every page lives under a version segment
and only the site root redirects. A link to `<site>/guide/fastapi/` therefore
404s where `<site>/latest/guide/fastapi/` resolves — silently, because
`mkdocs build --strict` validates links inside the built site and never sees an
absolute URL pointing back at it.

Six such links shipped before this check existed, including two in the README.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://andrelopes-code.github.io/depin/'
ALIAS = 'latest/'
IGNORED = {'site', '.venv', '.git', '.mypy_cache', '.ruff_cache', '.pytest_cache', 'mutants'}

_DEEP_LINK = re.compile(re.escape(SITE) + r'(?P<path>[A-Za-z0-9][A-Za-z0-9/_.#-]*)')


def _documents() -> list[Path]:
    return sorted(path for path in ROOT.rglob('*.md') if not set(path.relative_to(ROOT).parts) & IGNORED)


@pytest.mark.parametrize('document', _documents(), ids=lambda path: str(path.relative_to(ROOT)))
def test_every_deep_link_carries_the_version_alias(document: Path) -> None:
    """The site root may be linked bare; anything below it may not."""
    offenders = [
        match.group(0)
        for match in _DEEP_LINK.finditer(document.read_text(encoding='utf-8'))
        if not match.group('path').startswith(ALIAS)
    ]
    assert not offenders, (
        f'{document.relative_to(ROOT)} links below the site root without the '
        f'{ALIAS!r} alias, which 404s: {", ".join(offenders)}'
    )
