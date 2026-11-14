"""HTTP 蜜罐:伪装成常见后台登录页,记录所有请求和登录尝试。"""
import json
import time
from urllib.parse import parse_qs

from . import config
from .http_common import make_response, serve
from .ssh_server import _Limiter

limiter = _Limiter()

_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>WebAdmin - 系统登录</title>
<style>
 body{{margin:0;font-family:"Helvetica Neue",Arial,sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh}}
 .box{{background:#fff;padding:40px;width:340px;border-radius:6px;box-shadow:0 2px 12px rgba(0,0,0,.15)}}
 h2{{margin:0 0 6px;color:#333;font-size:20px}}
 .sub{{color:#999;font-size:12px;margin-bottom:24px}}
 input{{width:100%;box-sizing:border-box;padding:10px;margin-bottom:14px;border:1px solid #d9d9d9;border-radius:4px;font-size:14px}}
 button{{width:100%;padding:10px;background:#2f54eb;border:none;color:#fff;border-radius:4px;font-size:14px;cursor:pointer}}
 .err{{color:#f5222d;font-size:12px;margin-bottom:10px;{disp}}}
 .foot{{margin-top:24px;color:#bbb;font-size:11px;text-align:center}}
</style>
</head>
<body>
<div class="box">
 <h2>WebAdmin 控制台</h2>
 <div class="sub">企业应用管理平台 v3.2.1</div>
 {err}
 <form method="POST" action="/login">
  <input name="username" placeholder="用户名" autocomplete="off">
  <input name="password" type="password" placeholder="密码">
  <button type="submit">登 录</button>
 </form>
 <div class="foot">© 2023 WebAdmin Inc. All rights reserved.</div>
</div>
</body>
</html>"""


def _login_page(error: bool) -> bytes:
    err = '<div class="err">用户名或密码错误,请重试</div>' if error else ""
    return _LOGIN_PAGE.format(disp="" if error else "display:none", err=err).encode()


_404 = ("<html>\r\n<head><title>404 Not Found</title></head>\r\n<body>\r\n"
        "<center><h1>404 Not Found</h1></center>\r\n"
        f"<hr><center>{config.HTTP_SERVER_HEADER}</center>\r\n"
        "</body>\r\n</html>\r\n").encode()


class HTTPHoneypot:
    def __init__(self, storage):
        self._storage = storage

    async def handle(self, reader, writer, req, peer):
        src_ip, src_port = (peer[0], 0) if peer else ("unknown", 0)
        start = time.time()
        sid = self._storage.open_session(
            "http", src_ip, src_port, config.HTTP_PORT,
            meta={"user_agent": req.headers.get("user-agent", "")})

        # 记录请求本身(路径/方法/头),扫描器探测路径就靠这个发现
        body_text = ""
        if req.body:
            body_text = req.body.decode("utf-8", "replace")[:2048]
        self._storage.log_event(sid, start, "http", json.dumps({
            "method": req.method,
            "path": req.path,
            "headers": {k: v for k, v in req.headers.items()
                        if k in ("user-agent", "referer", "cookie", "authorization",
                                 "x-forwarded-for", "content-type")},
            "body": body_text,
        }, ensure_ascii=False))

        path = req.query_path
        if req.method == "GET" and path in ("/", "/login", "/index.html", "/admin"):
            resp = make_response(200, _login_page(False),
                                 server_header=config.HTTP_SERVER_HEADER)
        elif req.method == "POST" and path == "/login":
            form = parse_qs(req.body.decode("utf-8", "replace"))
            username = (form.get("username") or [""])[0][:256]
            password = (form.get("password") or [""])[0][:256]
            self._storage.log_auth(sid, username, password, success=False)
            # 永远提示错误,让爆破者继续试
            resp = make_response(200, _login_page(True),
                                 server_header=config.HTTP_SERVER_HEADER)
        elif path == "/robots.txt":
            resp = make_response(200, b"User-agent: *\nDisallow: /admin\nDisallow: /backup\n",
                                 "text/plain", server_header=config.HTTP_SERVER_HEADER)
        elif path == "/favicon.ico":
            resp = make_response(404, _404, server_header=config.HTTP_SERVER_HEADER)
        else:
            resp = make_response(404, _404, server_header=config.HTTP_SERVER_HEADER)

        writer.write(resp)
        await writer.drain()
        self._storage.close_session(sid)


async def start_http_server(storage):
    hp = HTTPHoneypot(storage)
    return await serve(config.BIND_HOST, config.HTTP_PORT, hp.handle,
                       limiter=limiter, name="http-honeypot")
