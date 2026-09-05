from depin import ScopeFrame, ScopeSeed


def test_scope_seed_provides_its_value_to_a_frame() -> None:
    frame = ScopeFrame()
    ScopeSeed(str, 'value', 'primary').apply(frame)

    assert frame.lookup_provided(str, 'primary') == 'value'
