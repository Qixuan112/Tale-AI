"""
Test unified handler registration system
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.function_caller import register_handler, _handler_registry, execute_function
from core.tools.registry import get_registry, ToolDefinition, ToolParameter


def test_handler_registration():
    """Test that handlers can be registered and called"""
    # Clear registry for clean test
    _handler_registry.clear()

    # Register a test handler
    def test_handler(parameters: dict) -> dict:
        return {"status": "success", "result": f"Hello {parameters.get('name', 'World')}"}

    register_handler("test_tool", test_handler)

    # Verify registration
    assert "test_tool" in _handler_registry
    assert _handler_registry["test_tool"] == test_handler

    # Test execution
    result = execute_function("test_tool", {"name": "Tale"})
    assert result["status"] == "success"
    assert result["result"] == "Hello Tale"

    print("[PASS] Handler registration test passed")


def test_registry_auto_registration():
    """Test that ToolRegistry automatically registers handlers"""
    # Clear for clean test
    _handler_registry.clear()

    # Create a test handler
    def custom_handler(parameters: dict) -> dict:
        return {"status": "success", "value": parameters.get("input", 0) * 2}

    # Register tool with handler in registry
    registry = get_registry()
    registry.register(
        ToolDefinition(
            name="test_double",
            description="Double a number",
            parameters=[ToolParameter("input", "Number to double")],
            handler=custom_handler
        )
    )

    # Verify handler was auto-registered
    assert "test_double" in _handler_registry

    # Test execution
    result = execute_function("test_double", {"input": 21})
    assert result["status"] == "success"
    assert result["value"] == 42

    print("[PASS] Registry auto-registration test passed")


def test_builtin_tool_definitions():
    """Test that all built-in tools are defined in registry"""
    registry = get_registry()
    tools = registry.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "browser_open",
        "browser_search",
        "weather_query",
        "calculator",
        "query_group_members",
        "take_photo",
        "generate_image",
        "draw_picture",
    }

    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    print(f"[PASS] Built-in tool definitions test passed ({len(tools)} tools)")


def test_unknown_function():
    """Test that unknown functions return proper error"""
    result = execute_function("nonexistent_tool", {})
    assert result["status"] == "failed"
    assert "未知的函数" in result["error"]

    print("[PASS] Unknown function test passed")


if __name__ == "__main__":
    print("Running handler registry tests...\n")
    test_builtin_tool_definitions()
    test_handler_registration()
    test_registry_auto_registration()
    test_unknown_function()
    print("\n[PASS] All tests passed!")
