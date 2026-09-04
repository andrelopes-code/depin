from depin import ScopeSeed


def test_scope_seed_provides_its_value_to_a_frame() -> None:
    class Frame:
        def __init__(self) -> None:
            self.provided: tuple[object, object, str | None] | None = None

        def provide(self, key: object, value: object, tag: str | None = None) -> None:
            self.provided = key, value, tag

    frame = Frame()
    ScopeSeed(str, 'value', 'primary').apply(frame)

    assert frame.provided == (str, 'value', 'primary')
