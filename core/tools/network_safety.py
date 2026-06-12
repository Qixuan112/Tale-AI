"""
网络安全工具函数 — SSRF 防护、响应大小限制
"""
import socket
import ipaddress
from typing import Optional
from urllib.parse import urlparse

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def is_private_ip(ip_str: str) -> bool:
    """检查 IP 地址是否属于私有/保留地址段"""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast
    except ValueError:
        return True  # 无法解析的地址视为不安全


def resolve_hostname(hostname: str) -> Optional[str]:
    """解析域名到 IP 地址（支持 IPv4 和 IPv6）"""
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for info in infos:
            return info[4][0]
        return None
    except socket.gaierror:
        return None


def validate_url(target_url: str) -> Optional[str]:
    """校验 URL 的 SSRF 安全性

    返回错误信息字符串（不安全）或 None（安全）
    """
    parsed = urlparse(target_url)
    # 限制协议为 http/https
    if parsed.scheme not in ("http", "https"):
        return f"不支持的协议: {parsed.scheme or '(空)'}"

    hostname = parsed.hostname
    if not hostname:
        return "无法解析的主机名"

    # 解析域名到 IP
    ip = resolve_hostname(hostname)

    if ip is None:
        return f"无法解析主机: {hostname}"

    # 检查是否为私有地址
    if is_private_ip(ip):
        return f"拒绝访问内网地址: {ip}"

    return None
