import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_example_app() -> None:
    from examples.fastapi_app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/users/1')
    assert r.json() == {'id': 1, 'name': 'Ana'}
