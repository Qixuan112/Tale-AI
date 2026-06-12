"""
天气工具 - 查询天气信息（使用 wttr.in API）
"""

import requests
from urllib.parse import quote


def query(city: str) -> dict:
    """查询城市天气，使用 wttr.in API

    Args:
        city: 城市名称，如 北京、上海

    Returns:
        dict: {"status": "success"|"error", "result": "...", "error": "..."}

    Examples:
        >>> query("北京")
        {"status": "success", "result": "☀️ +32°C 45% ↙15km/h", "tool": "weather_query"}

        >>> query("Tokyo")
        {"status": "success", "result": "☁️ +26°C 70% ↑10km/h", "tool": "weather_query"}

        >>> query("不存在的城市")
        {"status": "error", "error": "HTTP 404", "tool": "weather_query"}
    """
    try:
        encoded_city = quote(city, safe='')
        url = f"https://wttr.in/{encoded_city}?format=%C+%t+%h+%w"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            text = resp.text.strip()
            return {"status": "success", "result": text, "tool": "weather_query"}
        else:
            return {"status": "error", "error": f"HTTP {resp.status_code}", "tool": "weather_query"}
    except Exception as e:
        return {"status": "error", "error": str(e), "tool": "weather_query"}
