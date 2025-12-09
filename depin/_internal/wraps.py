import contextlib


def wrap_sync_gen(gen_fn, params):
    @contextlib.contextmanager
    def _ctx():
        gen = gen_fn(**params)
        try:
            value = next(gen)
            yield value
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    return _ctx()


@contextlib.asynccontextmanager
async def wrap_async_gen(gen_fn, params):
    """Wrapper para async generators."""
    gen = gen_fn(**params)
    try:
        value = await gen.__anext__()
        yield value
    finally:
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
