"""集中配置:全部可用环境变量覆盖,默认值只用于本地测试(全部 >1024,免 root)。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 监听地址:生产环境应绑定到蜜罐专用 VLAN 的接口地址
BIND_HOST = os.environ.get("HP_BIND_HOST", "127.0.0.1")

SSH_PORT = int(os.environ.get("HP_SSH_PORT", "2222"))
HTTP_PORT = int(os.environ.get("HP_HTTP_PORT", "8080"))
API_PORT = int(os.environ.get("HP_API_PORT", "8081"))

DB_PATH = os.environ.get("HP_DB_PATH", os.path.join(BASE_DIR, "data", "honeypot.db"))
HOST_KEY_PATH = os.environ.get("HP_HOST_KEY", os.path.join(BASE_DIR, "data", "ssh_host_key"))

# 前端构建产物目录(npm run build 的输出)
WEB_DIST = os.environ.get("HP_WEB_DIST", os.path.join(BASE_DIR, "web", "dist"))

# ---- 资源限制(防 DoS / 防被当跳板消耗资源)----
MAX_GLOBAL_CONN = int(os.environ.get("HP_MAX_GLOBAL_CONN", "100"))   # 全局并发连接上限
MAX_CONN_PER_IP = int(os.environ.get("HP_MAX_CONN_PER_IP", "10"))     # 单 IP 并发上限
SESSION_MAX_SECONDS = int(os.environ.get("HP_SESSION_MAX", "300"))    # 单会话最长存活
SESSION_IDLE_SECONDS = int(os.environ.get("HP_SESSION_IDLE", "60"))   # 空闲超时
MAX_LINE_LEN = 4096          # 单行输入上限
MAX_CMDS_PER_SESSION = 500   # 单会话命令数上限
MAX_HTTP_BODY = 64 * 1024    # HTTP 请求体上限
HTTP_READ_TIMEOUT = 15       # HTTP 读超时(防 slowloris)

# 伪装身份
FAKE_HOSTNAME = os.environ.get("HP_FAKE_HOSTNAME", "srv-db-01")
HTTP_SERVER_HEADER = "nginx/1.18.0"
