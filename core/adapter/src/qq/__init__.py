"""
QQ适配器

基于 NapCat/OneBot 11 协议实现。

Required:
    pip install websockets aiohttp

Usage:
    from core.adapter import AdapterManager

    manager = AdapterManager()
    await manager.start_adapter("qq", {
        "ws_url": "ws://localhost:3001",
        "http_url": "http://localhost:3000"
    })
"""

from .adapter import QQAdapter

__all__ = ["QQAdapter"]
