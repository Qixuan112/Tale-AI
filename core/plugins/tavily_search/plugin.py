"""
Tavily Search Plugin
====================
Provides AI-optimized web search and content extraction via Tavily API.

Tools:
  tavily_search  — AI-powered web search
  tavily_extract — Extract raw content from URLs
"""

import os
from typing import Any, Dict, List

from core.plugin import PluginBase
from core.tools.registry import ToolDefinition, ToolParameter
from core.llm.context.section import PromptSection


class TavilySearchPlugin(PluginBase):
    """Tavily AI search plugin."""

    def _activate(self) -> None:
        pass

    def _deactivate(self) -> None:
        pass

    # ------------------------------------------------------------------
    # ToolProvider
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="tavily_search",
                description="AI-optimized web search via Tavily API",
                parameters=[
                    ToolParameter("query", "Search query string"),
                    ToolParameter(
                        "max_results", "Number of results (1-10, default 5)",
                        required=False, default="5",
                    ),
                    ToolParameter(
                        "search_depth", "Search depth: basic (fast) or advanced (deep)",
                        required=False, default="basic",
                    ),
                ],
            ),
            ToolDefinition(
                name="tavily_extract",
                description="Extract raw content from web pages via Tavily API",
                parameters=[
                    ToolParameter(
                        "urls", "Comma-separated list of URLs to extract",
                    ),
                ],
            ),
        ]

    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        if func_name == "tavily_search":
            return self._tool_search(parameters)
        elif func_name == "tavily_extract":
            return self._tool_extract(parameters)
        return {"status": "failed", "error": f"Unknown tool: {func_name}"}

    # ------------------------------------------------------------------
    # Tavily client
    # ------------------------------------------------------------------

    def _get_client(self):
        """Get TavilyClient instance. API key from config or env var."""
        try:
            from tavily import TavilyClient
        except ImportError:
            raise ImportError(
                "tavily-python not installed. Run: pip install tavily-python"
            )
        api_key = self.config.get("api_key") or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "Tavily API key not configured. "
                "Set api_key in plugin config or TAVILY_API_KEY env var."
            )
        return TavilyClient(api_key=api_key)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_search(self, params: dict) -> dict:
        try:
            client = self._get_client()
            max_results = min(int(params.get("max_results", 5)), 10)
            depth = params.get("search_depth", "basic")
            if depth not in ("basic", "advanced"):
                depth = "basic"
            result = client.search(
                query=params["query"],
                max_results=max_results,
                search_depth=depth,
            )
            return {
                "status": "success",
                "results": result.get("results", []),
            }
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        except ImportError as e:
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            return {"status": "failed", "error": f"Tavily API error: {e}"}

    def _tool_extract(self, params: dict) -> dict:
        try:
            client = self._get_client()
            urls_str = params["urls"]
            urls = [u.strip() for u in urls_str.split(",") if u.strip()]
            if not urls:
                return {"status": "failed", "error": "URL list is empty"}
            result = client.extract(urls=urls)
            return {
                "status": "success",
                "results": result.get("results", []),
            }
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        except ImportError as e:
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            return {"status": "failed", "error": f"Tavily API error: {e}"}

    # ------------------------------------------------------------------
    # PromptSectionProvider
    # ------------------------------------------------------------------

    def get_prompt_sections(self) -> List[tuple]:
        section = PromptSection(
            name="tavily_tools",
            content=self._build_prompt(),
            cacheable=True,
            order=51,
        )
        return [("chat", section)]

    def _build_prompt(self) -> str:
        return """
## Tavily Search Tools

AI-optimized web search and content extraction:

1. **tavily_search** — AI web search
   - `query`: Search keywords
   - `max_results`: Results count (1-10, default 5)
   - `search_depth`: "basic" (fast) or "advanced" (deep)

2. **tavily_extract** — Web content extraction
   - `urls`: Comma-separated URL list

Usage: <act>use tavily_search to search for latest AI news</act>
""".strip()
