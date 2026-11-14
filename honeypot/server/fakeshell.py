"""假 shell:纯字符串模拟,绝不执行任何真实命令、绝不开任何网络连接。

这是"不能当跳板"的核心之一:
- 没有任何 subprocess / os.system
- wget/curl/ssh/nc 等联网命令只返回伪造输出,不产生真实外联
"""
import time

from . import config

_FAKE_FS = {
    "/": ["bin", "boot", "dev", "etc", "home", "lib", "opt", "proc", "root",
          "run", "sbin", "srv", "sys", "tmp", "usr", "var"],
    "/root": ["backup.tar.gz", "deploy.sh", ".bash_history", ".ssh"],
    "/home": ["deploy", "www-data"],
    "/etc": ["passwd", "shadow", "hosts", "nginx", "ssh", "crontab"],
    "/var/log": ["auth.log", "syslog", "nginx", "mysql"],
    "/tmp": [],
}

_PASSWD = """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
mysql:x:109:117:MySQL Server,,,:/nonexistent:/bin/false
deploy:x:1000:1000:Deploy,,,:/home/deploy:/bin/bash
"""


class FakeShell:
    def __init__(self, username: str = "root"):
        self.user = username
        self.hostname = config.FAKE_HOSTNAME
        self.home = "/root" if username == "root" else f"/home/{username}"
        self.cwd = self.home
        self.history: list[str] = []
        # 每个会话独立的文件系统视图,补上当前用户家目录
        self._fs = dict(_FAKE_FS)
        self._fs.setdefault(self.home, ["Desktop", ".bashrc", ".profile"])

    # ---- 外观 ----

    def prompt(self) -> str:
        ch = "#" if self.user == "root" else "$"
        shown = "~" if self.cwd == self.home else self.cwd
        return f"{self.user}@{self.hostname}:{shown}{ch} "

    def motd(self) -> str:
        return (
            "Welcome to Ubuntu 20.04.6 LTS (GNU/Linux 5.4.0-169-generic x86_64)\n"
            "\n"
            " * Documentation:  https://help.ubuntu.com\n"
            " * Management:     https://landscape.canonical.com\n"
            " * Support:        https://ubuntu.com/advantage\n"
            "\n"
            f"Last login: {time.strftime('%a %b %d %H:%M:%S %Y')} from 10.20.3.17\n"
        )

    # ---- 命令处理:返回 (输出文本, 是否退出会话) ----

    def handle(self, line: str) -> tuple[str, bool]:
        line = line.strip()
        if not line:
            return "", False
        self.history.append(line)

        # 支持 `a; b` 顺序执行
        if ";" in line:
            out = []
            for part in line.split(";"):
                o, exit_ = self.handle(part)
                if o:
                    out.append(o)
                if exit_:
                    return "\n".join(out), True
            return "\n".join(out), False

        parts = line.split()
        cmd, args = parts[0], parts[1:]

        if cmd in ("exit", "logout", "quit"):
            return "logout", True
        if cmd in ("sh", "bash", "zsh", "su"):
            return "", False
        if cmd == "cd":
            target = args[0] if args else ("~" )
            return self._cd(target), False
        if cmd == "pwd":
            return self.cwd, False
        if cmd == "ls":
            return self._ls(args), False
        if cmd == "whoami":
            return self.user, False
        if cmd == "id":
            if self.user == "root":
                return "uid=0(root) gid=0(root) groups=0(root)", False
            return f"uid=1000({self.user}) gid=1000({self.user}) groups=1000({self.user}),27(sudo)", False
        if cmd == "hostname":
            return self.hostname, False
        if cmd == "uname":
            if "-a" in args:
                return (f"Linux {self.hostname} 5.4.0-169-generic #187-Ubuntu SMP "
                        "x86_64 x86_64 x86_64 GNU/Linux"), False
            return "Linux", False
        if cmd == "date":
            return time.strftime("%a %b %d %H:%M:%S %Z %Y"), False
        if cmd == "uptime":
            return f" {time.strftime('%H:%M:%S')} up 137 days,  3:42,  1 user,  load average: 0.08, 0.03, 0.01", False
        if cmd == "history":
            return "\n".join(f"  {i+1}  {c}" for i, c in enumerate(self.history)), False
        if cmd == "echo":
            return " ".join(a for a in args if not a.startswith(">")).replace(">", "").strip(), False
        if cmd == "cat":
            return self._cat(args), False
        if cmd in ("ifconfig", "ip"):
            return _IFCONFIG, False
        if cmd in ("netstat", "ss"):
            return _NETSTAT, False
        if cmd == "ps":
            return _PS, False
        if cmd in ("w", "who"):
            return f"{time.strftime('%H:%M:%S')} up 137 days,  1 user,  load average: 0.08, 0.03, 0.01\n" \
                   f"USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT\n" \
                   f"{self.user:<8} pts/0    10.20.3.17       {time.strftime('%H:%M')}    0.00s  0.02s  0.00s w", False
        if cmd == "df":
            return _DF, False
        if cmd == "free":
            return _FREE, False
        if cmd in ("wget", "curl"):
            return self._download(cmd, args), False
        if cmd in ("chmod", "chown", "mkdir", "touch", "rm", "mv", "cp", "tar"):
            return "", False  # 假装成功,什么都不发生
        if cmd in ("ssh", "scp", "sftp", "nc", "ncat", "telnet", "ftp"):
            # 关键:伪造外联失败,绝不开真实连接
            target = args[-1] if args else ""
            return f"{cmd}: connect to host {target} port 22: Connection timed out", False
        if cmd == "sudo":
            if self.user == "root":
                sub = " ".join(args)
                return self.handle(sub) if sub else ("", False)
            return f"[sudo] password for {self.user}: \n{self.user} is not in the sudoers file. This incident will be reported.", False
        if cmd in ("python", "python3", "perl", "ruby", "php"):
            return "", False

        return f"-bash: {cmd}: command not found", False

    # ---- 内部 ----

    def _cd(self, target: str) -> str:
        if target in ("~", ""):
            self.cwd = self.home
        elif target == "..":
            self.cwd = "/" if self.cwd == "/" else self.cwd.rsplit("/", 1)[0] or "/"
        elif target == "-":
            pass
        else:
            path = target if target.startswith("/") else f"{self.cwd.rstrip('/')}/{target}"
            if path in self._fs:
                self.cwd = path
            else:
                return f"-bash: cd: {target}: No such file or directory"
        return ""

    def _ls(self, args: list[str]) -> str:
        path = self.cwd
        for a in args:
            if not a.startswith("-"):
                path = a if a.startswith("/") else f"{self.cwd.rstrip('/')}/{a}"
        entries = self._fs.get(path)
        if entries is None:
            return f"ls: cannot access '{path}': No such file or directory"
        if "-l" in args or "-la" in args or "-al" in args:
            lines = [f"total {4 * len(entries)}"]
            for e in entries:
                lines.append(f"drwxr-xr-x  2 {self.user} {self.user} 4096 Nov 12 09:31 {e}")
            return "\n".join(lines)
        return "  ".join(entries)

    def _cat(self, args: list[str]) -> str:
        files = [a for a in args if not a.startswith("-")]
        if not files:
            return ""
        f = files[0]
        if f.endswith("/etc/passwd") or f == "/etc/passwd":
            return _PASSWD.rstrip("\n")
        if f == "/etc/shadow":
            return f"cat: /etc/shadow: Permission denied"
        if f == "/etc/hostname":
            return self.hostname
        if f == "/etc/hosts":
            return f"127.0.0.1 localhost\n10.20.3.5 {self.hostname}"
        if f == "/etc/os-release":
            return 'PRETTY_NAME="Ubuntu 20.04.6 LTS"\nNAME="Ubuntu"\nVERSION_ID="20.04"'
        return f"cat: {f}: No such file or directory"

    def _download(self, cmd: str, args: list[str]) -> str:
        """伪造下载成功——不产生任何真实网络请求,URL 会随命令一起被记录。"""
        url = next((a for a in args if "://" in a), args[-1] if args else "")
        host = url.split("://", 1)[-1].split("/")[0] or "unknown"
        fname = url.rstrip("/").rsplit("/", 1)[-1] or "index.html"
        if cmd == "wget":
            return (
                f"--{time.strftime('%Y-%m-%d %H:%M:%S')}--  {url}\n"
                f"Resolving {host} ({host})... 45.132.9.21\n"
                f"Connecting to {host} ({host})|45.132.9.21|:80... connected.\n"
                f"HTTP request sent, awaiting response... 200 OK\n"
                f"Length: 2452 (2.4K) [text/x-sh]\n"
                f"Saving to: '{fname}'\n\n"
                f"{fname}        100%[===================>]   2.39K  --.-KB/s    in 0s\n\n"
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} (212 MB/s) - '{fname}' saved [2452/2452]"
            )
        return f"  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current\n" \
               f"                                 Dload  Upload   Total   Spent    Left  Speed\n" \
               f"100  2452  100  2452    0     0  81250      0 --:--:-- --:--:-- --:--:-- 81250"


_IFCONFIG = """eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.20.3.5  netmask 255.255.255.0  broadcast 10.20.3.255
        inet6 fe80::a00:27ff:fe4e:66a1  prefixlen 64  scopeid 0x20<link>
        ether 08:00:27:4e:66:a1  txqueuelen 1000  (Ethernet)
        RX packets 18234561  bytes 12938475213 (12.9 GB)
        TX packets 9821345  bytes 8231456123 (8.2 GB)

lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0"""

_NETSTAT = """Active Internet connections (servers and established)
Proto Recv-Q Send-Q Local Address           Foreign Address         State
tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN
tcp        0      0 127.0.0.1:3306          0.0.0.0:*               LISTEN
tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN
tcp        0      0 10.20.3.5:22            10.20.3.17:51234        ESTABLISHED"""

_PS = """  PID TTY          TIME CMD
    1 ?        00:03:12 systemd
  423 ?        00:00:41 sshd
  891 ?        01:24:10 mysqld
 1024 ?        00:12:03 nginx
12847 pts/0    00:00:00 bash
12901 pts/0    00:00:00 ps"""

_DF = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        96G   41G   51G  45% /
tmpfs           2.0G     0  2.0G   0% /dev/shm"""

_FREE = """              total        used        free      shared  buff/cache   available
Mem:        2048000      812344      198432        1024     1037224     1123456
Swap:       1048572           0     1048572"""
