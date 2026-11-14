"""极简 asyncio HTTP/1.1 解析,蜜罐和 API 共用。只支持够用的子集。"""
import asyncio

from . import config


class Request:
    def __init__(self, method, path, version, headers, body):
        self.method = method
        self.path = path
        self.version = version
        self.headers = headers  # dict, key 小写
        self.body = body

    @property
    def query_path(self):
        return self.path.split("?", 1)[0]


async def read_request(reader: asyncio.StreamReader) -> Request | None:
    try:
        line = await asyncio.wait_for(reader.readline(), config.HTTP_READ_TIMEOUT)
    except (asyncio.TimeoutError, ConnectionError):
        return None
    if not line or line in (b"\r\n", b"\n"):
        return None
    try:
        method, path, version = line.decode("latin1").rstrip("\r\n").split(" ", 2)
    except ValueError:
        return None
    headers = {}
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), config.HTTP_READ_TIMEOUT)
        except (asyncio.TimeoutError, ConnectionError):
            return None
        if line in (b"\r\n", b"\n", b""):
            break
        k, _, v = line.decode("latin1").partition(":")
        headers[k.strip().lower()] = v.strip()
    body = b""
    try:
        cl = int(headers.get("content-length") or 0)
    except ValueError:
        cl = 0
    if 0 < cl <= config.MAX_HTTP_BODY:
        try:
            body = await asyncio.wait_for(reader.readexactly(cl), config.HTTP_READ_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            return None
    return Request(method, path, version, headers, body)


_STATUS = {200: "OK", 301: "Moved Permanently", 302: "Found", 400: "Bad Request",
           401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
           405: "Method Not Allowed", 500: "Internal Server Error"}


def make_response(status: int, body: bytes = b"",
                  content_type: str = "text/html; charset=utf-8",
                  extra_headers: dict | None = None,
                  server_header: str | None = None) -> bytes:
    lines = [f"HTTP/1.1 {status} {_STATUS.get(status, 'OK')}"]
    if server_header:
        lines.append(f"Server: {server_header}")
    lines.append(f"Content-Type: {content_type}")
    lines.append(f"Content-Length: {len(body)}")
    lines.append("Connection: close")
    for k, v in (extra_headers or {}).items():
        lines.append(f"{k}: {v}")
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("latin1") + body


async def serve(host: str, port: int, handler, limiter=None, name: str = "http"):
    """handler(reader, writer, request, peer) -> None,每个连接调用一次(Connection: close)。"""

    async def _conn(reader, writer):
        peer = writer.get_extra_info("peername")
        ip = peer[0] if peer else "unknown"
        if limiter and not limiter.acquire(ip):
            writer.close()
            return
        try:
            req = await read_request(reader)
            if req is not None:
                await handler(reader, writer, req, peer)
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            if limiter:
                limiter.release(ip)

    server = await asyncio.start_server(_conn, host, port)
    return server
