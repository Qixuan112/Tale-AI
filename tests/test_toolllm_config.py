"""
Task #3 - Issue #133: ToolLLM配置覆盖Bug验证测试

测试ToolLLM在初始化时，构造函数参数无法覆盖services.yaml配置的bug。

问题描述：
当通过构造函数传入api_key/model/url参数时，这些参数被provider_manager.get_api_config覆盖，
导致无法在运行时动态指定配置。

预期行为：
构造函数参数应优先于配置文件，允许运行时覆盖。

测试策略：
1. Bug验证测试：证明当前实现中构造函数参数被忽略
2. 修复验证测试：验证修复后构造函数参数能正确覆盖
3. 配置系统测试：验证配置加载和优先级逻辑
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestToolLLMConfigBug:
    """Bug验证测试组 - 证明配置覆盖bug存在"""

    def test_constructor_params_ignored_bug(self):
        """
        Bug验证：构造函数参数被services.yaml覆盖

        当前实现中，即使传入api_key/model/url参数，
        provider_manager.get_api_config的返回值仍会覆盖这些参数。

        预期失败：此测试应该失败，证明bug存在
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            # 模拟配置文件返回值
            mock_pm.get_api_config.return_value = {
                'api_key': 'config_key',
                'model': 'config_model',
                'url': 'http://config.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    # 通过构造函数传入参数
                    tool_llm = ToolLLM(
                        api_key='custom_key',
                        model='custom_model',
                        url='http://custom.url'
                    )

                    # 预期：构造函数参数应优先
                    # 实际：被配置文件覆盖（bug）
                    assert tool_llm.api_key == 'custom_key', "Bug存在：构造函数api_key被配置覆盖"
                    assert tool_llm.model == 'custom_model', "Bug存在：构造函数model被配置覆盖"
                    assert tool_llm.base_url == 'http://custom.url', "Bug存在：构造函数url被配置覆盖"

    def test_config_file_takes_precedence_bug(self):
        """
        Bug验证：配置文件错误地优先于构造函数参数

        预期失败：此测试应该失败，证明优先级错误
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'yaml_key',
                'model': 'yaml_model',
                'url': 'http://yaml.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    tool_llm = ToolLLM(
                        api_key='override_key',
                        model='override_model',
                        url='http://override.url'
                    )

                    # Bug：配置文件值错误地取代了构造函数参数
                    assert tool_llm.api_key != 'yaml_key', "Bug：api_key应使用构造函数参数"
                    assert tool_llm.model != 'yaml_model', "Bug：model应使用构造函数参数"
                    assert tool_llm.base_url != 'http://yaml.url', "Bug：url应使用构造函数参数"


class TestToolLLMConfigFix:
    """修复验证测试组 - 验证修复后的正确行为"""

    def test_constructor_params_override_config(self):
        """
        修复验证：构造函数参数应优先于配置文件

        修复后，应按以下优先级：
        1. 构造函数参数（最高）
        2. services.yaml配置
        3. 默认值（最低）
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'config_key',
                'model': 'config_model',
                'url': 'http://config.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    tool_llm = ToolLLM(
                        api_key='custom_key',
                        model='custom_model',
                        url='http://custom.url'
                    )

                    # 修复后：构造函数参数应优先
                    assert tool_llm.api_key == 'custom_key'
                    assert tool_llm.model == 'custom_model'
                    assert tool_llm.base_url == 'http://custom.url'

    def test_partial_override(self):
        """
        修复验证：部分参数覆盖，其余从配置文件读取

        只传入部分参数时，未传入的参数应从配置文件读取
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'config_key',
                'model': 'config_model',
                'url': 'http://config.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    # 只覆盖api_key
                    tool_llm = ToolLLM(api_key='custom_key')

                    assert tool_llm.api_key == 'custom_key'
                    assert tool_llm.model == 'config_model'
                    assert tool_llm.base_url == 'http://config.url'

    def test_no_override_uses_config(self):
        """
        修复验证：不传参数时使用配置文件

        构造函数不传参数时，应完全使用配置文件
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'config_key',
                'model': 'config_model',
                'url': 'http://config.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    tool_llm = ToolLLM()

                    assert tool_llm.api_key == 'config_key'
                    assert tool_llm.model == 'config_model'
                    assert tool_llm.base_url == 'http://config.url'


class TestToolLLMConfigSystem:
    """配置系统测试组 - 验证配置加载和优先级"""

    def test_config_loader_integration(self):
        """
        配置系统：验证provider_manager.get_api_config正确调用
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'test_key',
                'model': 'test_model',
                'url': 'http://test.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    ToolLLM()

                    # 验证正确调用配置加载器
                    mock_pm.get_api_config.assert_called_once_with("tool_llm")

    def test_empty_config_fallback(self):
        """
        配置系统：配置为空时的fallback行为
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {}

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    from core.llm.toolllm import ToolLLM

                    tool_llm = ToolLLM()

                    # 空配置时应使用默认值
                    assert tool_llm.api_key == ""
                    assert tool_llm.model == ""
                    assert tool_llm.base_url == ""

    def test_provider_initialization(self):
        """
        配置系统：验证OpenAICompatibleProvider正确初始化
        """
        with patch('core.llm.toolllm.provider_manager') as mock_pm:
            mock_pm.get_api_config.return_value = {
                'api_key': 'test_key',
                'model': 'test_model',
                'url': 'http://test.url'
            }

            with patch('core.llm.toolllm.get_registry'):
                with patch('core.llm.toolllm.create_tool_context'):
                    with patch('core.llm.toolllm.OpenAICompatibleProvider') as mock_provider:
                        from core.llm.toolllm import ToolLLM

                        tool_llm = ToolLLM(
                            api_key='custom_key',
                            model='custom_model',
                            url='http://custom.url'
                        )

                        # 验证provider使用正确的参数初始化
                        mock_provider.assert_called_once()
                        call_kwargs = mock_provider.call_args[1]
                        assert call_kwargs['api_key'] == 'custom_key'
                        assert call_kwargs['base_url'] == 'http://custom.url'
                        assert call_kwargs['default_model'] == 'custom_model'
