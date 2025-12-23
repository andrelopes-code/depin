import contextlib


def wrap_sync_gen(gen_fn, params):
    @contextlib.contextmanager
    def _ctx():
        gen = gen_fn(**params)
        exception_to_raise = None
        try:
            value = next(gen)
            yield value
        except Exception as e:
            exception_to_raise = e
        finally:
            try:
                if exception_to_raise:
                    gen.throw(type(exception_to_raise), exception_to_raise, exception_to_raise.__traceback__)
                else:
                    next(gen)
            except StopIteration:
                pass
            except Exception:
                if exception_to_raise:
                    raise exception_to_raise
                raise

    return _ctx()


@contextlib.asynccontextmanager
async def wrap_async_gen(gen_fn, params):
    gen = gen_fn(**params)
    exception_to_raise = None
    try:
        value = await gen.__anext__()
        yield value
    except Exception as e:
        exception_to_raise = e
    finally:
        try:
            if exception_to_raise:
                await gen.athrow(type(exception_to_raise), exception_to_raise, exception_to_raise.__traceback__)
            else:
                await gen.__anext__()
        except StopAsyncIteration:
            pass
        except Exception:
            if exception_to_raise:
                raise exception_to_raise
            raise
