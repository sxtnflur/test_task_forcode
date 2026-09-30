import asyncio

from client import ProxyClientPool


def test_client_is_reused_for_the_same_proxy():
    async def run():
        pool = ProxyClientPool(timeout=5)
        first = pool.get("http://proxy-a:8080")
        try:
            # Создавать клиент на каждый запрос медленно: для того же прокси возвращается тот же клиент
            assert pool.get("http://proxy-a:8080") is first
            assert pool.get("http://proxy-b:8080") is not first
        finally:
            await pool.aclose()

    asyncio.run(run())


def test_clients_are_closed():
    async def run():
        pool = ProxyClientPool(timeout=5)
        client = pool.get("http://proxy-a:8080")

        await pool.aclose()

        assert client.is_closed
        # После закрытия создается новый клиент, а не возвращается закрытый
        new_client = pool.get("http://proxy-a:8080")
        assert new_client is not client
        await pool.aclose()

    asyncio.run(run())
