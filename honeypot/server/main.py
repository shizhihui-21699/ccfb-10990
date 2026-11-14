"""蜜罐主入口:同时拉起 SSH 蜜罐、HTTP 蜜罐、查询 API。

运行:  python -m server.main
"""
import asyncio
import logging

from . import api, config, http_server, ssh_server
from .storage import Storage

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("honeypot")


async def main():
    storage = Storage(config.DB_PATH)

    ssh_srv = await ssh_server.start_ssh_server(storage)
    log.info("SSH  honeypot listening on %s:%d", config.BIND_HOST, config.SSH_PORT)

    http_srv = await http_server.start_http_server(storage)
    log.info("HTTP honeypot listening on %s:%d", config.BIND_HOST, config.HTTP_PORT)

    api_srv = await api.start_api_server(storage)
    log.info("API + console on http://%s:%d", config.BIND_HOST, config.API_PORT)

    async with ssh_srv, http_srv, api_srv:
        await asyncio.gather(
            ssh_srv.wait_closed(), http_srv.wait_closed(), api_srv.wait_closed())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
