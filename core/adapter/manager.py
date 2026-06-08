import os
import sys
import json
import importlib.util
from typing import Dict, Type, Optional, List, Callable, Awaitable, Any
from pathlib import Path
import asyncio

from .base import BaseAdapter
from .event import PlatformEvent, PlatformType
from ..utils import get_logger

logger = get_logger(__name__)


class AdapterManager:
    """适配器管理器

    负责适配器的注册、生命周期管理和消息转发。
    复用 KiraAI 的自动扫描机制。

    Example:
        async def on_event(event: PlatformEvent):
            logger.info(f"Received: {event.content.text}")

        manager = AdapterManager(config, on_event)
        await manager.start_adapter("qq", qq_config)
    """

    # 类级别的注册表，所有实例共享
    _registry: Dict[str, Type[BaseAdapter]] = {}
    _manifests: Dict[str, dict] = {}
    _schemas: Dict[str, list] = {}
    _scanned = False

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[PlatformEvent, str], Awaitable[None]]] = None
    ):
        """初始化管理器

        Args:
            config: 全局配置
            event_callback: 全局事件回调函数
        """
        self.config = config or {}
        self.event_callback = event_callback
        self._adapters: Dict[str, BaseAdapter] = {}
        self._enabled_adapters: List[str] = []
        # platform.value → [instance_name, ...] 索引，支持按平台类型查找
        self._platform_index: Dict[str, List[str]] = {}

        # 自动扫描适配器（只执行一次）
        if not AdapterManager._scanned:
            src_dir = Path(__file__).parent / "src"
            self.scan_adapters(src_dir)
            AdapterManager._scanned = True

    @classmethod
    def scan_adapters(cls, src_dir: Path):
        """扫描适配器目录自动注册

        遍历 src/ 目录下的所有子目录，查找并注册适配器。
        每个适配器目录应包含:
        - manifest.json: 适配器元数据
        - schema.json: 配置Schema（可选）
        - adapter.py: 适配器实现

        Args:
            src_dir: 适配器源码目录
        """
        if not src_dir.exists():
            logger.info(f"Adapter source directory not found: {src_dir}")
            return

        logger.info(f"Scanning adapters from: {src_dir}")

        for adapter_dir in src_dir.iterdir():
            if not adapter_dir.is_dir():
                continue

            adapter_id = adapter_dir.name
            manifest_path = adapter_dir / "manifest.json"
            schema_path = adapter_dir / "schema.json"
            adapter_file = adapter_dir / "adapter.py"

            # 必须存在 manifest.json
            if not manifest_path.exists():
                continue

            # 读取 manifest
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                # 使用 manifest 中的 id 或目录名
                adapter_id = manifest.get("id") or adapter_id
                cls._manifests[adapter_id] = manifest
            except Exception as e:
                logger.info(f"Failed to load manifest for {adapter_id}: {e}")
                continue

            # 读取 schema（可选）
            if schema_path.exists():
                try:
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        cls._schemas[adapter_id] = json.load(f)
                except Exception as e:
                    logger.info(f"Failed to load schema for {adapter_id}: {e}")
                    cls._schemas[adapter_id] = []
            else:
                cls._schemas[adapter_id] = []

            # 动态导入适配器类
            if adapter_file.exists():
                try:
                    # 方式：将 adapter.py 作为包的子模块导入
                    # 先确保父包路径在 sys.modules 中
                    package_name = f"core.adapter.src.{adapter_id}"
                    module_name = f"{package_name}.adapter"

                    # 如果包不存在，创建一个空的包模块（利用已有的 __init__.py）
                    if package_name not in sys.modules:
                        init_file = adapter_dir / "__init__.py"
                        if init_file.exists():
                            init_spec = importlib.util.spec_from_file_location(
                                package_name, init_file,
                                submodule_search_locations=[str(adapter_dir)]
                            )
                            init_module = importlib.util.module_from_spec(init_spec)
                            sys.modules[package_name] = init_module
                            init_spec.loader.exec_module(init_module)
                        else:
                            # 没有 __init__.py，创建一个命名空间包
                            ns_module = type(sys)(package_name)
                            ns_module.__path__ = [str(adapter_dir)]
                            ns_module.__package__ = package_name
                            ns_module.__name__ = package_name
                            sys.modules[package_name] = ns_module

                    spec = importlib.util.spec_from_file_location(
                        module_name, adapter_file
                    )
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # 查找适配器类（继承自 BaseAdapter 且不是 BaseAdapter 本身）
                    adapter_class = None
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            issubclass(attr, BaseAdapter) and
                            attr is not BaseAdapter):
                            adapter_class = attr
                            break

                    if adapter_class:
                        cls._registry[adapter_id] = adapter_class
                        logger.info(f"  ✓ Registered adapter: {adapter_id} ({manifest.get('name', 'Unknown')})")
                    else:
                        logger.info(f"  ✗ No adapter class found in: {adapter_id}")

                except Exception as e:
                    logger.info(f"  ✗ Failed to load adapter {adapter_id}: {e}")

        logger.info(f"Adapter scan complete. Found {len(cls._registry)} adapter(s).")

    @classmethod
    def get_adapter_class(cls, adapter_id: str) -> Optional[Type[BaseAdapter]]:
        """获取适配器类

        Args:
            adapter_id: 适配器ID

        Returns:
            适配器类或 None
        """
        return cls._registry.get(adapter_id)

    @classmethod
    def list_adapters(cls) -> List[str]:
        """列出所有可用适配器ID

        Returns:
            适配器ID列表
        """
        return list(cls._registry.keys())

    @classmethod
    def get_adapter_info(cls, adapter_id: str) -> Optional[dict]:
        """获取适配器信息

        Args:
            adapter_id: 适配器ID

        Returns:
            包含 name, version, author, description 等信息的字典
        """
        manifest = cls._manifests.get(adapter_id, {})
        return {
            "id": adapter_id,
            "name": manifest.get("name", adapter_id),
            "version": manifest.get("version", "unknown"),
            "author": manifest.get("author", "unknown"),
            "description": manifest.get("description", ""),
        }

    @classmethod
    def get_schema(cls, adapter_id: str) -> list:
        """获取适配器配置Schema

        Args:
            adapter_id: 适配器ID

        Returns:
            配置项列表
        """
        return cls._schemas.get(adapter_id, [])

    async def start_adapter(self, adapter_id: str, adapter_config: dict, adapter_type: str = None) -> bool:
        """启动指定适配器

        Args:
            adapter_id: 适配器实例ID（唯一标识）
            adapter_config: 适配器配置
            adapter_type: 适配器类型（用于查找适配器类，默认为 adapter_id）

        Returns:
            启动是否成功

        Raises:
            ValueError: 适配器已存在或未找到适配器类
            Exception: 适配器启动过程中的其他异常
        """
        if adapter_id in self._adapters:
            msg = f"Adapter {adapter_id} is already running"
            logger.info(msg)
            raise ValueError(msg)

        actual_type = adapter_type or adapter_id
        adapter_class = self.get_adapter_class(actual_type)
        if not adapter_class:
            msg = f"Adapter {actual_type} not found"
            logger.info(msg)
            raise ValueError(msg)

        # 创建适配器实例
        adapter = adapter_class(adapter_config, self.event_callback)
        adapter.adapter_id = adapter_id

        # 启动适配器
        await adapter.start()

        self._adapters[adapter_id] = adapter
        self._enabled_adapters.append(adapter_id)

        # 更新 platform 索引
        platform_key = adapter.platform.value
        if platform_key not in self._platform_index:
            self._platform_index[platform_key] = []
        if adapter_id not in self._platform_index[platform_key]:
            self._platform_index[platform_key].append(adapter_id)

        logger.info(f"Started adapter: {adapter_id} (platform={platform_key})")
        return True

    async def stop_adapter(self, adapter_id: str) -> bool:
        """停止指定适配器

        Args:
            adapter_id: 适配器ID

        Returns:
            停止是否成功
        """
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            logger.info(f"Adapter {adapter_id} is not running")
            return False

        try:
            # 从 platform 索引中移除
            platform_key = adapter.platform.value
            if platform_key in self._platform_index:
                if adapter_id in self._platform_index[platform_key]:
                    self._platform_index[platform_key].remove(adapter_id)
                if not self._platform_index[platform_key]:
                    del self._platform_index[platform_key]

            await adapter.stop()
            del self._adapters[adapter_id]
            self._enabled_adapters.remove(adapter_id)
            logger.info(f"Stopped adapter: {adapter_id}")
            return True
        except Exception as e:
            logger.info(f"Error stopping adapter {adapter_id}: {e}")
            return False

    async def stop_all(self):
        """停止所有适配器"""
        for adapter_id in list(self._adapters.keys()):
            await self.stop_adapter(adapter_id)

    def get_adapter(self, adapter_id: str) -> Optional[BaseAdapter]:
        """获取运行中的适配器实例

        Args:
            adapter_id: 适配器ID

        Returns:
            适配器实例或 None
        """
        return self._adapters.get(adapter_id)

    def list_running_adapters(self) -> List[str]:
        """列出正在运行的适配器

        Returns:
            运行中的适配器ID列表
        """
        return list(self._adapters.keys())

    def resolve_adapter_id(self, adapter_id_or_platform: str) -> Optional[str]:
        """解析适配器标识为运行中的实例名

        支持两种输入：
        1. 精确的实例名（如 "QQ Adapter_2"）
        2. 平台类型（如 "qq"），自动找到该平台下的第一个运行实例

        这样即使实例昵称变了，只要 platform 不变就能正确路由。

        Args:
            adapter_id_or_platform: 适配器实例名或平台类型

        Returns:
            运行中的适配器实例名，找不到返回 None
        """
        # 1. 精确匹配实例名
        if adapter_id_or_platform in self._adapters:
            return adapter_id_or_platform

        # 2. 按 platform 类型查找
        instances = self._platform_index.get(adapter_id_or_platform.lower())
        if instances:
            return instances[0]

        return None

    async def send_message(
        self,
        adapter_id: str,
        target_id: str,
        text: Optional[str] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> bool:
        """通过指定适配器发送消息

        支持通过实例名或 platform 类型查找适配器。
        例如 adapter_id="qq" 会自动找到该平台下第一个运行中的实例。

        Args:
            adapter_id: 适配器实例名或平台类型
            target_id: 目标ID（用户ID或群ID）
            text: 文本内容
            images: 图片URL列表
            **kwargs: 其他参数

        Returns:
            发送是否成功
        """
        from .event import MessageContent

        # 解析 adapter_id（支持实例名或 platform 类型）
        resolved = self.resolve_adapter_id(adapter_id)
        if not resolved:
            logger.info(f"No running adapter for: {adapter_id}")
            return False

        adapter = self._adapters[resolved]

        content = MessageContent(
            text=text,
            images=images or [],
            at_targets=kwargs.get("at_targets") or [],
            reply_to=kwargs.get("reply_to"),
        )

        try:
            return await adapter.send_message(target_id, content, **kwargs)
        except Exception as e:
            logger.info(f"Error sending message via {resolved}: {e}")
            return False

    async def broadcast(
        self,
        target_adapters: Optional[List[str]] = None,
        target_id: Optional[str] = None,
        text: Optional[str] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """广播消息到多个适配器

        Args:
            target_adapters: 目标适配器ID列表，None表示所有运行中的适配器
            target_id: 目标ID
            text: 文本内容
            **kwargs: 其他参数

        Returns:
            各适配器发送结果的字典
        """
        adapters = target_adapters or self.list_running_adapters()
        results = {}

        for adapter_id in adapters:
            results[adapter_id] = await self.send_message(
                adapter_id, target_id or "", text, **kwargs
            )

        return results
