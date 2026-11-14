# 低交互蜜罐(SSH + HTTP)

内网横向扫描检测:asyncio 后端模拟 SSH/HTTP 服务,全量记录攻击行为,
Svelte 前端支持按原始节奏回放会话、来源 IP 统计、口令排行。

## 结构

```
honeypot/
├── server/               # Python asyncio 后端
│   ├── main.py           # 入口:同时拉起三个服务
│   ├── config.py         # 配置(环境变量可覆盖)
│   ├── ssh_server.py     # SSH 蜜罐(asyncssh,接受任意口令,假 shell)
│   ├── http_server.py    # HTTP 蜜罐(伪装后台登录页)
│   ├── fakeshell.py      # 假 shell:纯字符串模拟,零真实执行
│   ├── http_common.py    # 极简 HTTP/1.1 解析
│   ├── api.py            # 查询 API + 前端静态文件
│   └── storage.py        # SQLite 存储(全部参数化 SQL)
├── web/                  # Svelte 前端(会话回放 / 统计)
├── tests/simulate.py     # 攻击行为模拟器(自测用)
└── deploy/honeypot.service  # systemd 加固单元示例
```

## 快速开始

```bash
python3 -m venv ../.venv && ../.venv/bin/pip install asyncssh
../.venv/bin/python -m server.main          # 启动蜜罐
../.venv/bin/python tests/simulate.py all   # 另开终端,模拟攻击

cd web && npm install && npm run build      # 构建前端(已构建可跳过)
```

- SSH 蜜罐: `127.0.0.1:2222`(任意口令可入)
- HTTP 蜜罐: `http://127.0.0.1:8080`(伪后台登录页)
- 控制台: `http://127.0.0.1:8081`(会话回放 + 统计)

生产部署用 `HP_BIND_HOST` 绑到蜜罐 VLAN 接口;端口可用 `HP_SSH_PORT` 等覆盖
(绑 22/80 需要 root 或 setcap,建议用 iptables REDIRECT 代替)。

## 反跳板隔离设计(重点)

蜜罐本身绝不能成为攻击者的内网跳板,分四层:

**1. 应用层(代码保证,最重要)**
- 假 shell 是纯字符串匹配:没有任何 `subprocess`/`os.system`,命令永远不会被真实执行
- `wget`/`curl`/`ssh`/`nc` 等联网命令只返回伪造输出,**不产生任何真实外联连接**
- SSH 不实现 `connection_requested`(direct-tcpip)→ asyncssh 默认拒绝一切端口转发
- 不实现 SFTP/子系统;HTTP 蜜罐不做任何代理转发

**2. 资源层(防 DoS 消耗)**
- 全局/单 IP 并发连接上限(`HP_MAX_GLOBAL_CONN` / `HP_MAX_CONN_PER_IP`)
- 会话最长 300s、空闲 60s 强制断开;单行输入、请求体、命令数均有上限
- HTTP 读超时防 slowloris

**3. 系统层(见 deploy/honeypot.service)**
- 专用非 root 用户运行,`NoNewPrivileges`、`ProtectSystem=strict`、
  `ProtectHome`、`PrivateTmp`、系统调用过滤
- 工作目录只读,仅数据目录可写

**4. 网络层(部署时配置,代码管不到)**
- 蜜罐放独立 VLAN/安全域,交换机 ACL 或防火墙:
  - **允许**:任意内网段 → 蜜罐端口的入站(这是要被探测的)
  - **拒绝**:蜜罐 → 任何地址的出站新建连接(包括 DNS),并在防火墙上
    对这类拒绝日志告警——蜜罐主动外联本身就是最高危信号
- 参考 nftables 规则(蜜罐 IP 10.99.0.10):

```
table inet honeypot {
  chain output {
    type filter hook output priority 0; policy drop;
    ip saddr 10.99.0.10 ct state established,related accept
    ip saddr 10.99.0.10 log prefix "HONEYPOT-EGRESS " drop
  }
}
```

## 数据与回放

- 所有会话/认证尝试/事件存 SQLite(`data/honeypot.db`),事件带毫秒级相对时间戳
- 前端回放按原始时间间隔播放,SSH 输入逐字敲入(模拟打字),支持
  0.5–8x 倍速、暂停、拖动进度条
- 统计页:来源 IP 排行、常用口令/用户名排行、HTTP 探测路径排行

## API

| 路径 | 说明 |
|---|---|
| `GET /api/sessions` | 会话列表(含事件数/认证数) |
| `GET /api/sessions/{id}` | 会话详情 + 全部事件 + 认证尝试 |
| `GET /api/stats` | 汇总统计(IP/口令/用户名/路径排行) |
