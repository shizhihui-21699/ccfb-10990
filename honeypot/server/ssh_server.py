"""SSH 蜜罐:asyncssh 实现完整握手,接受任意口令,进假 shell。

反跳板:
- 不实现 connection_requested / unix_connection_requested
  → asyncssh 默认拒绝一切 direct-tcpip / 端口转发请求
- 不实现 SFTP / 子系统
- shell 是 FakeShell 纯模拟,exec 请求也只走 FakeShell
"""
import asyncio
import time

import asyncssh

from . import config
from .fakeshell import FakeShell


class _Limiter:
    """全局 + 单 IP 并发连接限制。"""

    def __init__(self):
        self.total = 0
        self.per_ip: dict[str, int] = {}

    def acquire(self, ip: str) -> bool:
        if self.total >= config.MAX_GLOBAL_CONN:
            return False
        if self.per_ip.get(ip, 0) >= config.MAX_CONN_PER_IP:
            return False
        self.total += 1
        self.per_ip[ip] = self.per_ip.get(ip, 0) + 1
        return True

    def release(self, ip: str):
        self.total = max(0, self.total - 1)
        if ip in self.per_ip:
            self.per_ip[ip] -= 1
            if self.per_ip[ip] <= 0:
                del self.per_ip[ip]


limiter = _Limiter()


class HoneypotSSHServer(asyncssh.SSHServer):
    def __init__(self, storage):
        self._storage = storage
        self._session_id: int | None = None
        self._start = 0.0
        self._src_ip = ""
        self._username = ""

    def connection_made(self, conn):
        peer = conn.get_extra_info("peername")
        self._src_ip = peer[0] if peer else "unknown"
        if not limiter.acquire(self._src_ip):
            conn.close()  # 超并发上限直接断开
            return
        src_port = peer[1] if peer else 0
        self._start = time.time()
        self._session_id = self._storage.open_session(
            "ssh", self._src_ip, src_port, config.SSH_PORT,
            meta={"client_version": conn.get_extra_info("client_version") or ""})

    def connection_lost(self, exc):
        if self._session_id is not None:
            self._storage.close_session(self._session_id)
            limiter.release(self._src_ip)

    def begin_auth(self, username) -> bool:
        self._username = username
        return True  # 要求认证(这样才能收集口令)

    def password_auth_supported(self) -> bool:
        return True

    def public_key_auth_supported(self) -> bool:
        return False

    def kbdint_auth_supported(self) -> bool:
        return False

    def validate_password(self, username, password) -> bool:
        # 接受任意口令,全部记录——口令排行统计的数据来源
        self._storage.log_auth(self._session_id, username, password, success=True)
        return True

    def session_requested(self):
        return HoneypotSSHSession(self._storage, self._session_id,
                                  self._start, self._username)


class HoneypotSSHSession(asyncssh.SSHServerSession):
    def __init__(self, storage, session_id: int, start: float, username: str):
        self._storage = storage
        self._sid = session_id
        self._start = start
        self._shell = FakeShell(username or "root")
        self._chan = None
        self._buf = ""
        self._cmd_count = 0
        self._idle_handle: asyncio.TimerHandle | None = None
        self._max_handle: asyncio.TimerHandle | None = None

    # ---- 通道协商 ----

    def connection_made(self, chan):
        self._chan = chan
        loop = asyncio.get_running_loop()
        self._max_handle = loop.call_later(config.SESSION_MAX_SECONDS, self._kick)
        self._reset_idle()

    def connection_lost(self, exc):
        for h in (self._idle_handle, self._max_handle):
            if h:
                h.cancel()

    def pty_requested(self, term_type, term_size, term_modes):
        return True

    def shell_requested(self):
        motd = self._shell.motd()
        self._out(motd + self._shell.prompt())
        return True

    def exec_requested(self, command):
        # 非交互 exec(如 ssh host 'cmd'):也只走假 shell,记录后回应
        self._storage.log_event(self._sid, self._start, "in", command)
        out, _ = self._shell.handle(command)
        if out:
            self._out(out + "\n")
        self._chan.exit(0)
        self._chan.close()
        return True

    def subsystem_requested(self, subsystem):
        return False  # 拒绝 SFTP 等一切子系统

    # ---- 交互输入 ----

    def data_received(self, data, datatype):
        self._reset_idle()
        for ch in data:
            if ch in ("\r", "\n"):
                self._enter()
            elif ch in ("\x7f", "\x08"):  # backspace
                if self._buf:
                    self._buf = self._buf[:-1]
                    self._chan.write("\b \b")
            elif ch == "\x03":  # Ctrl-C
                self._buf = ""
                self._chan.write("^C\n" + self._shell.prompt())
            elif ch == "\x04":  # Ctrl-D
                if not self._buf:
                    self._out("logout\n")
                    self._chan.exit(0)
                    self._chan.close()
                    return
            elif ch == "\x1b":  # 转义序列(方向键等),忽略
                pass
            elif ch >= " " or ch == "\t":
                if len(self._buf) < config.MAX_LINE_LEN:
                    self._buf += ch
                    self._chan.write(ch)  # 回显

    def eof_received(self):
        return False

    # ---- 内部 ----

    def _enter(self):
        line = self._buf
        self._buf = ""
        self._chan.write("\n")
        if line.strip():
            self._cmd_count += 1
            self._storage.log_event(self._sid, self._start, "in", line)
            out, exit_ = self._shell.handle(line)
            if out:
                self._out(out + "\n")
            if exit_ or self._cmd_count >= config.MAX_CMDS_PER_SESSION:
                self._chan.exit(0)
                self._chan.close()
                return
        self._out(self._shell.prompt())

    def _out(self, text: str):
        self._storage.log_event(self._sid, self._start, "out", text)
        self._chan.write(text)

    def _reset_idle(self):
        if self._idle_handle:
            self._idle_handle.cancel()
        self._idle_handle = asyncio.get_running_loop().call_later(
            config.SESSION_IDLE_SECONDS, self._kick)

    def _kick(self):
        try:
            self._chan.write("\nConnection timed out.\n")
            self._chan.close()
        except Exception:
            pass


def ensure_host_key(path: str) -> str:
    import os
    if not os.path.exists(path):
        key = asyncssh.generate_private_key("ssh-rsa", key_size=2048)
        key.write_private_key(path)
        os.chmod(path, 0o600)
    return path


async def start_ssh_server(storage):
    ensure_host_key(config.HOST_KEY_PATH)

    class _Factory(HoneypotSSHServer):
        def __init__(self):
            super().__init__(storage)

    server = await asyncssh.create_server(
        _Factory, config.BIND_HOST, config.SSH_PORT,
        server_host_keys=[config.HOST_KEY_PATH],
        server_version="SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.7",
    )
    return server
