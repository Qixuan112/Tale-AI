"""
网络安全工具函数 — SSRF 防护、响应大小限制

为了消除 TOCTOU / DNS rebinding 风险，这里提供 safe_request：
先解析并校验域名的所有 IP，然后把连接固定（pin）到通过校验的 IP，
同时保留原始 Host 头与 TLS SNI / 证书校验，确保「校验的 IP」就是
「实际连接的 IP」。
"""
import socket
import ipaddress
import threading
from typing import Optional, List, Tuple
from urllib.parse import urlparse

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

# 额外的被拦截网段（标准库 is_private 等属性未覆盖的部分）
_EXTRA_BLOCKED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),  # RFC 6598 共享地址段（运营商级 NAT）
]


def is_private_ip(ip_str: str) -> bool:
    """检查 IP 地址是否属于私有/保留地址段"""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 无法解析的地址视为不安全
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
        return True
    # 检查标准库未覆盖的额外网段（如 RFC 6598 100.64.0.0/10）
    for network in _EXTRA_BLOCKED_NETWORKS:
        if addr.version == network.version and addr in network:
            return True
    return False


def resolve_all_ips(hostname: str) -> List[str]:
    """解析域名到所有 IP 地址（支持 IPv4 和 IPv6），去重后返回"""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    ips: List[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def resolve_hostname(hostname: str) -> Optional[str]:
    """解析域名到 IP 地址（返回第一个，保留向后兼容）"""
    ips = resolve_all_ips(hostname)
    return ips[0] if ips else None


def _validate_hostname(hostname: str) -> Tuple[Optional[str], List[str]]:
    """校验域名解析出的全部 IP

    返回 (错误信息或 None, 通过校验的 IP 列表)
    """
    ips = resolve_all_ips(hostname)
    if not ips:
        return f"无法解析主机: {hostname}", []
    # 任意一个解析结果落在内网/保留段即拒绝（防止部分记录绕过）
    for ip in ips:
        if is_private_ip(ip):
            return f"拒绝访问内网地址: {ip}", []
    return None, ips


def validate_url(target_url: str) -> Optional[str]:
    """校验 URL 的 SSRF 安全性

    返回错误信息字符串（不安全）或 None（安全）

    注意：这是一次性的预检，单独使用时仍存在 TOCTOU 风险
    （调用方后续若自行发起请求会重新解析 DNS）。需要真正发起请求时，
    请改用 safe_request / safe_get，它会把连接固定到已校验的 IP。
    """
    parsed = urlparse(target_url)
    # 限制协议为 http/https
    if parsed.scheme not in ("http", "https"):
        return f"不支持的协议: {parsed.scheme or '(空)'}"

    hostname = parsed.hostname
    if not hostname:
        return "无法解析的主机名"

    err, _ = _validate_hostname(hostname)
    return err


# ---------------------------------------------------------------------------
# 固定 IP 的安全请求实现（消除 TOCTOU / DNS rebinding）
# ---------------------------------------------------------------------------

class SSRFValidationError(Exception):
    """SSRF 校验失败时抛出，message 为人类可读的拒绝原因"""


# ---------------------------------------------------------------------------
# 线程安全的连接固定（pin）
#
# 早期实现是在请求期间临时替换 urllib3 全局的 create_connection，再于 finally
# 还原——这在并发下不安全：本进程的工具执行 / 图片下载都跑在 ThreadPoolExecutor
# 上，两个 safe_request 并发时，一个线程的 socket 可能被另一个线程的固定 IP 连接，
# 或 finally 提前还原导致后续连接重新走 DNS（重新打开 DNS rebinding 缺口）。
#
# 改为：把「主机名 -> 已校验 IP」映射放进 thread-local，并在 create_connection 上
# 安装「一次性、幂等」的全局钩子。钩子只按【当前线程】的映射改写目标 IP，
# 不同线程互不影响；未设置映射的线程/主机完全透明，等价于原始行为。
# ---------------------------------------------------------------------------

_pin_local = threading.local()
_pin_install_lock = threading.Lock()
_orig_create_connection = None


def _ensure_pin_hook_installed() -> None:
    """在 urllib3.util.connection.create_connection 上安装一次性钩子（线程安全、幂等）。"""
    global _orig_create_connection
    from urllib3.util import connection as urllib3_connection

    if getattr(urllib3_connection.create_connection, "_taleai_pin_hook", False):
        return
    with _pin_install_lock:
        if getattr(urllib3_connection.create_connection, "_taleai_pin_hook", False):
            return
        _orig_create_connection = urllib3_connection.create_connection

        def _pinned_create_connection(address, *args, **kwargs):
            host, port = address[0], address[1]
            pins = getattr(_pin_local, "pins", None)
            if pins:
                pinned = pins.get(host)
                if pinned:
                    return _orig_create_connection((pinned, port), *args, **kwargs)
            return _orig_create_connection(address, *args, **kwargs)

        _pinned_create_connection._taleai_pin_hook = True
        urllib3_connection.create_connection = _pinned_create_connection


def safe_request(method: str, url: str, requests_mod=None, **kwargs):
    """SSRF 安全的 HTTP 请求：解析 -> 校验所有 IP -> 固定连接到已校验 IP

    - 保留原始 Host 头与 TLS SNI / 证书校验（verify 透传给 requests）。
    - 强制 allow_redirects=False；重定向需由调用方逐跳重新校验。
    - 校验失败抛出 SSRFValidationError。
    - 线程安全：固定信息存放于 thread-local，并发请求互不干扰。

    requests_mod：可选注入 requests 模块（便于在未全局导入时复用调用方的引用）。
    返回 requests.Response。
    """
    if requests_mod is None:
        import requests as requests_mod  # 局部导入，避免硬依赖

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(f"不支持的协议: {parsed.scheme or '(空)'}")
    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("无法解析的主机名")

    # 如果 host 本身就是 IP 字面量，直接校验即可，无需 DNS
    try:
        ipaddress.ip_address(hostname)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if is_private_ip(hostname):
            raise SSRFValidationError(f"拒绝访问内网地址: {hostname}")
        pinned_ip = hostname
    else:
        err, ips = _validate_hostname(hostname)
        if err:
            raise SSRFValidationError(err)
        pinned_ip = ips[0]

    # 始终禁用自动重定向，交由调用方逐跳校验
    kwargs["allow_redirects"] = False

    # 在当前线程的 thread-local 映射里登记「hostname -> 已校验 IP」，
    # 用 had_prev/prev 支持同线程嵌套/重入（如重定向到同一 host）。
    _ensure_pin_hook_installed()
    pins = getattr(_pin_local, "pins", None)
    if pins is None:
        pins = {}
        _pin_local.pins = pins
    had_prev = hostname in pins
    prev = pins.get(hostname)
    pins[hostname] = pinned_ip

    session = requests_mod.Session()
    try:
        return session.request(method, url, **kwargs)
    finally:
        if had_prev:
            pins[hostname] = prev
        else:
            pins.pop(hostname, None)
        session.close()


def safe_get(url: str, requests_mod=None, **kwargs):
    """safe_request 的 GET 便捷封装"""
    return safe_request("get", url, requests_mod=requests_mod, **kwargs)
