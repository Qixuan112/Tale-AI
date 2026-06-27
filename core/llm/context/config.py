"""
Context configuration — loading and applying context.yaml settings.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

import yaml


@dataclass
class AgentContextConfig:
    """Per-agent context section configuration."""
    agent_name: str
    cache_strategy: str = "single_message"  # "single_message" | "multi_message"
    sections: List[Dict[str, Any]] = field(default_factory=list)

    def get_section_order(self) -> Dict[str, int]:
        return {s["name"]: s.get("order", 0) for s in self.sections}

    def get_cacheable_map(self) -> Dict[str, bool]:
        # 仅返回 YAML 中显式声明了 cacheable 的 section，避免用默认值覆盖 section 自身的设置
        return {s["name"]: s["cacheable"] for s in self.sections if "cacheable" in s}


@dataclass
class ContextConfig:
    """Top-level context configuration."""
    defaults: Dict[str, Any] = field(default_factory=lambda: {"cache_strategy": "single_message"})
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_cache_strategy(self, agent_name: str) -> str:
        agent = self.agents.get(agent_name, {})
        return agent.get("cache_strategy", self.defaults.get("cache_strategy", "single_message"))

    def get_agent_config(self, agent_name: str) -> Optional[AgentContextConfig]:
        agent = self.agents.get(agent_name)
        if agent is None:
            return None
        return AgentContextConfig(
            agent_name=agent_name,
            cache_strategy=agent.get("cache_strategy", self.defaults.get("cache_strategy", "single_message")),
            sections=agent.get("sections", []),
        )

    def apply_to(self, agent_context: "AgentContext") -> None:
        """Apply this config's ordering and cacheability to an AgentContext."""
        agent_cfg = self.get_agent_config(agent_context.agent_name)
        if agent_cfg is None:
            return

        # Apply ordering
        order_map = agent_cfg.get_section_order()
        if order_map:
            agent_context.reorder(order_map)

        # Apply cacheable flags
        # 仅对 YAML 中显式声明 cacheable 的 section 应用，未声明的保留 section 自身的值
        cache_map = agent_cfg.get_cacheable_map()
        for section_name, cacheable in cache_map.items():
            section = agent_context.get_section(section_name)
            if section:
                section.cacheable = cacheable

        # 任何带动态内容提供器的 section 强制保持非缓存，避免动态内容被缓存后变陈旧
        for section in agent_context.sections:
            if getattr(section, "_content_provider", None) is not None:
                section.cacheable = False

    @classmethod
    def from_yaml(cls, path: str) -> "ContextConfig":
        """Load from a YAML file. Returns default config if file is missing."""
        if not os.path.isfile(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            defaults=data.get("defaults", {}),
            agents=data.get("agents", {}),
        )


def load_context_config(data_dir: str = None) -> ContextConfig:
    """Load context config from the default location.

    Tries ``data/config/context.yaml`` first, then falls back to defaults.
    """
    if data_dir is None:
        data_dir = os.environ.get("TALE_DATA_DIR", "data")
    path = os.path.join(data_dir, "config", "context.yaml")
    return ContextConfig.from_yaml(path)
