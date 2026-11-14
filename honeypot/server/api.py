"""查询 API + 前端静态文件服务(供 Svelte 控制台使用)。"""
import json
import mimetypes
import os

from . import config
from .http_common import make_response, serve

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


def _json(data, status=200) -> bytes:
    return make_response(status, json.dumps(data, ensure_ascii=False).encode(),
                         "application/json; charset=utf-8")


class API:
    def __init__(self, storage):
        self._storage = storage

    async def handle(self, reader, writer, req, peer):
        path = req.query_path
        if path == "/api/sessions":
            resp = _json({"sessions": self._storage.list_sessions()})
        elif path.startswith("/api/sessions/"):
            try:
                sid = int(path.rsplit("/", 1)[1])
            except ValueError:
                sid = -1
            detail = self._storage.get_session(sid)
            resp = _json(detail) if detail else _json({"error": "not found"}, 404)
        elif path == "/api/stats":
            resp = _json(self._storage.stats())
        else:
            resp = self._static(path)
        writer.write(resp)
        await writer.drain()

    def _static(self, path: str) -> bytes:
        if path in ("/", ""):
            path = "/index.html"
        # 防目录穿越
        safe = os.path.normpath(path).lstrip("/")
        if safe.startswith(".."):
            return _json({"error": "forbidden"}, 403)
        full = os.path.join(config.WEB_DIST, safe)
        if not os.path.isfile(full):
            # SPA fallback
            full = os.path.join(config.WEB_DIST, "index.html")
            if not os.path.isfile(full):
                return _json({"error": "frontend not built, run: cd web && npm run build"}, 404)
        with open(full, "rb") as f:
            body = f.read()
        ext = os.path.splitext(full)[1]
        return make_response(200, body, _MIME.get(ext, mimetypes.guess_type(full)[0]
                                                  or "application/octet-stream"))


async def start_api_server(storage):
    api = API(storage)
    return await serve(config.BIND_HOST, config.API_PORT, api.handle, name="api")
