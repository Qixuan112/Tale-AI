"""
网络安全工具函数 — SSRF 防护、响应大小限制
"""
import socket
import ipaddress
from typing import Optional
from urllib.parse import urlparse


# 私有地址段（RFC 1918 / RFC 4193 / RFC 3927 / RFC 6890）
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),       # 环回地址
    ipaddress.ip_network("169.254.0.0/16"),    # 链路本地
    ipaddress.ip_network("::1/128"),           # IPv6 环回
    ipaddress.ip_network("fc00::/7"),          # IPv6 唯一本地
    ipaddress.ip_network("fe80::/10"),         # IPv6 链路本地
    ipaddress.ip_network("0.0.0.0/8"),         # 当前网络
    ipaddress.ip_network("100.64.0.0/10"),     # 运营商级 NAT
    ipaddress.ip_network("198.18.0.0/15"),     # 基准测试
    ipaddress.ip_network("240.0.0.0/4"),       # 保留地址
]

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def is_private_ip(ip_str: str) -> bool:
    """检查 IP 地址是否属于私有/保留地址段"""
    try:
        addr = ipaddress.ip_address(ip_str)
        for network in _PRIVATE_RANGES:
            if addr in network:
                return True
        return False
    except ValueError:
        return True  # 无法解析的地址视为不安全


def resolve_hostname(hostname: str) -> Optional[str]:
    """解析域名到 IPv4 地址"""
    try:
        infos = socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_STREAM)
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
