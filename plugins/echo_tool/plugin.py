from typing import Any, Dict, List, Callable
from core.tools.registry import ToolDefinition, ToolParameter
from core.plugin import PluginBase, PluginManifest


class EchoPlugin(PluginBase):
    """Simple echo tool plugin for testing."""

    def _activate(self) -> None:
        pass

    def _deactivate(self) -> None:
        pass

    # ---- ToolProvider ----

    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="echo",
                description="Echo back the input message",
                parameters=[
                    ToolParameter(name="message", description="Message to echo"),
                ],
                handler=self.execute_tool,
            )
        ]

    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        msg = parameters.get("message", "")
        return {"status": "success", "echo": msg, "length": len(msg)}

    # ---- EventSubscriber ----

    def get_event_subscriptions(self) -> Dict[str, Callable]:
        def on_tool_executed(result, source):
            print(f"[EchoPlugin] Tool executed by {source}: {result}")

        return {"tool_executed": on_tool_executed}
