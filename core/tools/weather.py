"""
天气工具 - 查询天气信息
"""


def query(city: str) -> dict:
    """
    查询城市天气（模拟实现）
    
    Args:
        city: 城市名称
        
    Returns:
        天气信息字典
    """
    # 这里可以接入真实天气 API，如 OpenWeatherMap、和风天气等
    # 目前返回模拟数据
    
    mock_data = {
        "status": "success",
        "tool": "weather.query",
        "city": city,
        "data": f"{city}天气查询功能已触发（需要接入真实API）"
    }
    return mock_data
