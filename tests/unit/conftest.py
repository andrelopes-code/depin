from collections.abc import Generator

import pytest

from depin._core import overrides
from depin._core.markers import Token


@pytest.fixture
def interpreted_runtime() -> Generator[None]:
    marker = Token[object]('interpreted-runtime-marker')
    with overrides.pushed(marker, None, object()):
        yield
