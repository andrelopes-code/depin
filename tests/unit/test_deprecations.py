from importlib.metadata import version

import pytest

from depin._core.deprecations import Deprecation, emit_deprecation, validate_expiry
from depin.errors import InvalidScopeError


def test_deprecation_rejects_a_removal_version_that_is_not_later() -> None:
    with pytest.raises(InvalidScopeError, match='later than introduced version'):
        Deprecation(
            symbol='depin.Container.legacy_bind',
            action='Use Container.bind instead.',
            introduced_in='1.0.0',
            removal_in='1.0.0',
        )


def test_deprecation_warning_names_the_migration_window() -> None:
    deprecation = Deprecation(
        symbol='depin.Container.legacy_bind',
        action='Use Container.bind instead.',
        introduced_in='1.0.0',
        removal_in='2.0.0',
    )

    with pytest.warns(
        DeprecationWarning,
        match=r'depin\.Container\.legacy_bind.*Use Container\.bind instead.*1\.0\.0.*2\.0\.0',
    ):
        emit_deprecation(deprecation)


def test_expiry_validation_fails_for_registered_deprecations_at_package_version() -> None:
    deprecated_uses = (
        Deprecation(
            symbol='depin.Container.legacy_bind',
            action='Use Container.bind instead.',
            introduced_in='0.0.1',
            removal_in=version('pydepin'),
        ),
    )

    with pytest.raises(InvalidScopeError, match='removal version'):
        validate_expiry(deprecated_uses)
