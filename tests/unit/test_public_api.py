def test_public_api_imports() -> None:
    import depin

    assert hasattr(depin, 'Container')
    assert hasattr(depin, 'FrozenContainer')
    assert hasattr(depin, 'Registry')
    assert hasattr(depin, 'Scope')
    assert hasattr(depin, 'Token')
    assert hasattr(depin, 'Inject')
    assert hasattr(depin, 'Named')
    assert hasattr(depin, 'Tag')
    assert hasattr(depin, 'provides')
