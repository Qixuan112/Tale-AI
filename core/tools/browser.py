"""
浏览器工具 - 网页搜索与内容获取
搜索使用 duckduckgo_search 库，页面抓取使用 requests + BeautifulSoup
"""
import re
from typing import Optional, Dict

from ddgs import DDGS

# 尝试导入 requests 和 BeautifulSoup
try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def fetch_url(
    url: str,
    method: str = "get",
    headers: Optional[Dict] = None,
    timeout: int = 30,
    encoding: Optional[str] = None,
    verify_ssl: bool = True
) -> dict:
    """
    获取网页内容
    
    Args:
        url: 目标网址
        method: 请求方法 (get/post)
        headers: 自定义请求头
        timeout: 超时时间（秒）
        encoding: 指定编码，为空则自动检测
        verify_ssl: 是否验证 SSL 证书
        
    Returns:
        包含网页内容的结果字典
    """
    if not REQUESTS_AVAILABLE:
        return {
            "status": "failed",
            "tool": "browser.fetch_url",
            "error": "requests 未安装，请运行: pip install requests beautifulsoup4"
        }
    
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        if headers:
            default_headers.update(headers)
        
        request_kwargs = {
            "headers": default_headers,
            "timeout": timeout,
            "verify": verify_ssl
        }
        
        if method.lower() == "post":
            response = requests.post(url, **request_kwargs)
        else:
            response = requests.get(url, **request_kwargs)
        
        response.raise_for_status()
        
        if encoding:
            response.encoding = encoding
        else:
            response.encoding = response.apparent_encoding
        
        content = response.text
        
        return {
            "status": "success",
            "tool": "browser.fetch_url",
            "data": content[:1000] + "..." if len(content) > 1000 else content,
            "full_content": content,
            "content_length": len(content),
            "url": response.url,
            "status_code": response.status_code,
            "encoding": response.encoding
        }
    except Exception as e:
        return {
            "status": "failed",
            "tool": "browser.fetch_url",
            "error": str(e)
        }


def parse_html(
    content: str,
    selector: Optional[str] = None,
    extract_type: str = "text"
) -> dict:
    """
    解析 HTML 内容
    
    Args:
        content: HTML 内容
        selector: CSS 选择器，为空则返回整个文档
        extract_type: 提取类型 (text/html/links/images)
        
    Returns:
        包含解析结果的字典
    """
    if not REQUESTS_AVAILABLE:
        return {
            "status": "failed",
            "tool": "browser.parse_html",
            "error": "beautifulsoup4 未安装，请运行: pip install beautifulsoup4"
        }
    
    try:
        soup = BeautifulSoup(content, 'html.parser')
        
        if selector:
            from bs4 import SoupStrainer
            elements = soup.select(selector)
            
            if extract_type == "text":
                results = [elem.get_text(strip=True) for elem in elements]
            elif extract_type == "html":
                results = [str(elem) for elem in elements]
            elif extract_type == "links":
                results = []
                for elem in elements:
                    links = elem.find_all('a', href=True)
                    results.extend([{
                        "text": link.get_text(strip=True),
                        "href": link['href']
                    } for link in links])
            elif extract_type == "images":
                results = []
                for elem in elements:
                    images = elem.find_all('img', src=True)
                    results.extend([{
                        "alt": img.get('alt', ''),
                        "src": img['src']
                    } for img in images])
            else:
                results = [elem.get_text(strip=True) for elem in elements]
            
            return {
                "status": "success",
                "tool": "browser.parse_html",
                "data": f"找到 {len(elements)} 个元素",
                "count": len(elements),
                "results": results[:20],
                "selector": selector
            }
        else:
            title = soup.title.string if soup.title else ""
            text = soup.get_text(separator='\n', strip=True)
            links = [{"text": a.get_text(strip=True), "href": a['href']} 
                    for a in soup.find_all('a', href=True)][:20]
            
            return {
                "status": "success",
                "tool": "browser.parse_html",
                "data": text[:500] + "..." if len(text) > 500 else text,
                "full_text": text,
                "title": title,
                "links": links,
                "content_length": len(text)
            }
    except Exception as e:
        return {
            "status": "failed",
            "tool": "browser.parse_html",
            "error": str(e)
        }


def fetch_and_parse(
    url: str,
    selector: Optional[str] = None,
    extract_type: str = "text"
) -> dict:
    """
    获取并解析网页内容
    
    Args:
        url: 目标网址
        selector: CSS 选择器
        extract_type: 提取类型
        
    Returns:
        包含解析结果的字典
    """
    result = fetch_url(url)
    if result["status"] != "success":
        return result
    
    content = result.get("full_content", "")
    parse_result = parse_html(content, selector, extract_type)
    
    if parse_result["status"] != "success":
        return parse_result
    
    return {
        "status": "success",
        "tool": "browser.fetch_and_parse",
        "data": parse_result.get("data", ""),
        "full_text": parse_result.get("full_text", ""),
        "title": parse_result.get("title", ""),
        "url": result.get("url", url),
        "parse_results": parse_result.get("results", []),
        "links": parse_result.get("links", []),
        "content_length": parse_result.get("content_length", 0)
    }


def search_and_fetch(
    query: str,
    engine: str = "duckduckgo",
    max_results: int = 10
) -> dict:
    """
    使用 DuckDuckGo 搜索并获取结果
    
    Args:
        query: 搜索关键词
        engine: 保留参数，固定使用 DuckDuckGo
        max_results: 最大结果数，默认 10
        
    Returns:
        包含搜索结果的字典
    """
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
        
        results = [
            {
                "title": r.get("title", ""),
                "abstract": r.get("body", ""),
                "link": r.get("href", "")
            }
            for r in raw_results
        ]
        
        return {
            "status": "success",
            "tool": "browser.search_and_fetch",
            "data": f"找到 {len(results)} 条搜索结果",
            "query": query,
            "engine": "duckduckgo",
            "results": results,
        }
    except Exception as e:
        return {
            "status": "failed",
            "tool": "browser.search_and_fetch",
            "error": f"DuckDuckGo 搜索失败: {str(e)}",
            "query": query,
        }


def browser_search(query: str, engine: str = "duckduckgo") -> dict:
    """
    搜索并获取结果（兼容旧版接口）
    
    Args:
        query: 搜索关键词
        engine: 保留参数，固定使用 DuckDuckGo
        
    Returns:
        包含搜索结果的字典
    """
    return search_and_fetch(query, engine)


def extract_url_from_text(text: str) -> str:
    """从文本中提取 URL"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    match = re.search(url_pattern, text)
    if match:
        return match.group(0)
    return ""
