"""
Issue #163: Test AVAILABLE_TOOLS 验证

测试 toolllm.py 中 AVAILABLE_TOOLS 的功能性，确保移除冗余的 __import__ 后功能保持一致。

测试目标：
1. AVAILABLE_TOOLS 正确加载工具列表
2. 每个工具包含必需的字段（name, description, parameters）
3. 参数正确映射为字典格式
"""
import pytest


class TestAvailableTools:
    """测试 AVAILABLE_TOOLS 的功能性"""

    def test_available_tools_loaded(self):
        """验证 AVAILABLE_TOOLS 成功加载工具列表"""
        from core.llm.toolllm import AVAILABLE_TOOLS

        # AVAILABLE_TOOLS 应该是非空列表
        assert isinstance(AVAILABLE_TOOLS, list)
        assert len(AVAILABLE_TOOLS) > 0, "AVAILABLE_TOOLS 应包含至少一个工具"

    def test_available_tools_structure(self):
        """验证每个工具都有正确的结构"""
        from core.llm.toolllm import AVAILABLE_TOOLS

        for tool in AVAILABLE_TOOLS:
            # 每个工具必须包含 name, description, parameters
            assert "name" in tool, f"工具缺少 'name' 字段: {tool}"
            assert "description" in tool, f"工具缺少 'description' 字段: {tool}"
            assert "parameters" in tool, f"工具缺少 'parameters' 字段: {tool}"

            # name 和 description 必须是字符串
            assert isinstance(tool["name"], str), f"工具 name 应为字符串: {tool['name']}"
            assert isinstance(tool["description"], str), f"工具 description 应为字符串: {tool['description']}"

            # parameters 必须是字典
            assert isinstance(tool["parameters"], dict), f"工具 {tool['name']} 的 parameters 应为字典"

    def test_available_tools_match_registry(self):
        """验证 AVAILABLE_TOOLS 与 registry 保持一致"""
        from core.llm.toolllm import AVAILABLE_TOOLS
        from core.tools.registry import get_registry

        registry_tools = get_registry().list_tools()

        # 数量应该相同
        assert len(AVAILABLE_TOOLS) == len(registry_tools), \
            f"AVAILABLE_TOOLS 数量({len(AVAILABLE_TOOLS)})与注册表({len(registry_tools)})不匹配"

        # 验证每个工具的内容
        for available_tool in AVAILABLE_TOOLS:
            tool_name = available_tool["name"]

            # 在注册表中找到对应工具
            registry_tool = next((t for t in registry_tools if t.name == tool_name), None)
            assert registry_tool is not None, f"工具 {tool_name} 在注册表中未找到"

            # 验证 description 一致
            assert available_tool["description"] == registry_tool.description, \
                f"工具 {tool_name} 的 description 不一致"

            # 验证参数映射正确
            expected_params = {p.name: p.description for p in registry_tool.parameters}
            assert available_tool["parameters"] == expected_params, \
                f"工具 {tool_name} 的 parameters 不一致"

    def test_specific_tool_example(self):
        """验证特定工具的详细内容（以 browser_open 为例）"""
        from core.llm.toolllm import AVAILABLE_TOOLS

        # 查找 browser_open 工具
        browser_open = next((t for t in AVAILABLE_TOOLS if t["name"] == "browser_open"), None)
        assert browser_open is not None, "browser_open 工具应存在"

        # 验证结构
        assert browser_open["description"] == "打开指定网页"
        assert "url" in browser_open["parameters"]
        assert browser_open["parameters"]["url"] == "网页地址，如 https://www.baidu.com"
