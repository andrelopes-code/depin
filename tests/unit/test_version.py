import depin


def test_version_is_nonempty_string() -> None:
    assert isinstance(depin.__version__, str)
    assert depin.__version__
