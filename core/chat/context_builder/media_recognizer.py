"""MediaRecognizer - VLM图片识别模块

使用 VLM 识别消息中的图片，支持超时控制。
"""

import asyncio
import logging
from typing import List, Optional, Callable, Any
from pathlib import Path


logger = logging.getLogger(__name__)


class MediaRecognizer:
    """VLM 图片识别器，支持超时控制"""

    def __init__(
        self,
        vlm,
        timeout: float = 3.0,
        executor: Optional[Any] = None,
        download_func: Optional[Callable] = None
    ):
        """初始化图片识别器

        Args:
            vlm: VLM 实例（get_vlm_llm() 返回值）
            timeout: 识别超时秒数，默认3秒
            executor: 线程池执行器，用于异步执行阻塞操作
            download_func: 图片下载函数，接受URL返回本地路径
        """
        self._vlm = vlm
        self._timeout = timeout
        self._executor = executor
        self._download_func = download_func

    async def recognize_images(
        self,
        image_urls: List[str],
        prompt: str = "",
        max_images: int = 4
    ) -> Optional[str]:
        """识别图片内容（带超时控制）

        Args:
            image_urls: 图片 URL 列表
            prompt: 识别提示词（可选，默认为消息文本）
            max_images: 最大识别图片数量

        Returns:
            识别结果文本，失败或超时返回 None
        """
        if not image_urls:
            return None

        # 检查 VLM 是否可用
        if not self._is_vlm_available():
            logger.debug("VLM 不可用，跳过图片识别")
            return None

        try:
            # 下载图片到本地
            local_paths = await self._download_images(
                image_urls[:max_images]
            )

            if not local_paths:
                logger.warning("图片下载失败，跳过识别")
                return None

            # 执行识别（带超时）
            result = await asyncio.wait_for(
                self._recognize_with_vlm(prompt, local_paths),
                timeout=self._timeout
            )

            if result:
                logger.info("VLM 图片识别结果: %s", result[:200])
                return result

        except asyncio.TimeoutError:
            logger.warning("VLM 图片识别超时 (%.1fs)，返回占位符", self._timeout)
            return "[图片识别中...]"
        except Exception as e:
            logger.warning("VLM 图片识别失败: %s", e)

        return None

    def _is_vlm_available(self) -> bool:
        """检查 VLM 是否可用"""
        if not self._vlm:
            return False

        try:
            # 调用 _ensure_provider 检查配置
            return self._vlm._ensure_provider()
        except Exception:
            return False

    async def _download_images(self, urls: List[str]) -> List[str]:
        """下载图片到本地

        Args:
            urls: 图片 URL 列表

        Returns:
            本地路径列表
        """
        if not self._download_func or not self._executor:
            # 无下载函数，尝试直接使用 URL（可能是本地路径）
            return [url for url in urls if Path(url).is_file()]

        loop = asyncio.get_running_loop()
        local_paths = []

        for url in urls:
            try:
                path = await loop.run_in_executor(
                    self._executor,
                    self._download_func,
                    url
                )
                if path:
                    local_paths.append(path)
            except Exception as e:
                logger.debug("下载图片失败 %s: %s", url, e)

        return local_paths

    async def _recognize_with_vlm(
        self,
        prompt: str,
        local_paths: List[str]
    ) -> Optional[str]:
        """使用 VLM 识别图片

        Args:
            prompt: 识别提示词
            local_paths: 本地图片路径列表

        Returns:
            识别结果
        """
        if not self._executor:
            # 无线程池，直接同步调用（测试模式）
            return self._vlm.chat_with_image(
                prompt or "描述这张图片的内容",
                local_paths
            )

        # 异步执行阻塞的 VLM 调用
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._vlm.chat_with_image,
            prompt or "描述这张图片的内容",
            local_paths
        )

        return result
