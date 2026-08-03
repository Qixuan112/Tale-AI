"""Unit tests for MediaRecognizer

测试图片识别的各个场景：
- VLM 可用性检查
- 图片下载
- 识别超时处理
- 错误处理
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from core.chat.context_builder.media_recognizer import MediaRecognizer


@pytest.fixture
def mock_vlm():
    """创建 mock VLM"""
    vlm = Mock()
    vlm._ensure_provider = Mock(return_value=True)
    vlm.chat_with_image = Mock(return_value="这是一张图片")
    return vlm


@pytest.fixture
def mock_executor():
    """创建 mock 线程池执行器"""
    return Mock()


@pytest.fixture
def mock_download_func():
    """创建 mock 下载函数"""
    return Mock(return_value="/tmp/image.jpg")


@pytest.fixture
def media_recognizer(mock_vlm, mock_executor, mock_download_func):
    """创建图片识别器"""
    return MediaRecognizer(
        vlm=mock_vlm,
        timeout=3.0,
        executor=mock_executor,
        download_func=mock_download_func
    )


@pytest.mark.asyncio
async def test_recognize_images_empty_list(media_recognizer):
    """测试空图片列表"""
    result = await media_recognizer.recognize_images([])
    assert result is None


@pytest.mark.asyncio
async def test_recognize_images_vlm_unavailable():
    """测试 VLM 不可用时跳过识别"""
    mock_vlm = Mock()
    mock_vlm._ensure_provider = Mock(return_value=False)

    recognizer = MediaRecognizer(mock_vlm, timeout=3.0)
    result = await recognizer.recognize_images(["http://example.com/image.jpg"])

    assert result is None


@pytest.mark.asyncio
async def test_recognize_images_success(media_recognizer, mock_vlm):
    """测试成功识别图片"""
    with patch.object(media_recognizer, '_download_images',
                     return_value=["/tmp/img1.jpg"]):
        with patch.object(media_recognizer, '_recognize_with_vlm',
                         return_value="一只猫"):
            result = await media_recognizer.recognize_images(
                ["http://example.com/cat.jpg"],
                prompt="描述图片"
            )

    assert result == "一只猫"


@pytest.mark.asyncio
async def test_recognize_images_timeout(media_recognizer):
    """测试识别超时返回占位符"""
    async def slow_recognize(*args):
        await asyncio.sleep(5)  # 超过 3 秒超时
        return "结果"

    with patch.object(media_recognizer, '_download_images',
                     return_value=["/tmp/img1.jpg"]):
        with patch.object(media_recognizer, '_recognize_with_vlm',
                         side_effect=slow_recognize):
            result = await media_recognizer.recognize_images(
                ["http://example.com/image.jpg"]
            )

    assert result == "[图片识别中...]"


@pytest.mark.asyncio
async def test_recognize_images_download_failed(media_recognizer):
    """测试图片下载失败"""
    with patch.object(media_recognizer, '_download_images',
                     return_value=[]):
        result = await media_recognizer.recognize_images(
            ["http://example.com/image.jpg"]
        )

    assert result is None


@pytest.mark.asyncio
async def test_recognize_images_max_limit(media_recognizer):
    """测试最大图片数量限制"""
    urls = [f"http://example.com/img{i}.jpg" for i in range(10)]

    download_mock = AsyncMock(side_effect=lambda x: [f"/tmp/{i}.jpg" for i in range(len(x))])
    recognize_mock = AsyncMock(return_value="结果")

    with patch.object(media_recognizer, '_download_images', download_mock):
        with patch.object(media_recognizer, '_recognize_with_vlm', recognize_mock):
            await media_recognizer.recognize_images(urls, max_images=4)

    # 验证只下载了前4张
    download_mock.assert_called_once()
    downloaded_urls = download_mock.call_args[0][0]
    assert len(downloaded_urls) == 4


@pytest.mark.asyncio
async def test_download_images_no_func():
    """测试无下载函数时使用本地路径"""
    recognizer = MediaRecognizer(Mock(), timeout=3.0)

    with patch('pathlib.Path.is_file', return_value=True):
        result = await recognizer._download_images(["/local/img.jpg"])

    assert result == ["/local/img.jpg"]


@pytest.mark.asyncio
async def test_download_images_with_executor(mock_vlm, mock_executor, mock_download_func):
    """测试使用线程池下载图片"""
    recognizer = MediaRecognizer(mock_vlm, executor=mock_executor,
                                 download_func=mock_download_func)

    async def fake_executor(executor, func, *args):
        return func(*args)

    with patch('asyncio.get_running_loop') as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=fake_executor)

        result = await recognizer._download_images(["http://example.com/img.jpg"])

    assert "/tmp/image.jpg" in result


@pytest.mark.asyncio
async def test_recognize_with_vlm_no_executor(mock_vlm):
    """测试无线程池时直接同步调用"""
    recognizer = MediaRecognizer(mock_vlm, timeout=3.0, executor=None)

    result = await recognizer._recognize_with_vlm("描述", ["/tmp/img.jpg"])

    assert result == "这是一张图片"
    mock_vlm.chat_with_image.assert_called_once_with("描述", ["/tmp/img.jpg"])


@pytest.mark.asyncio
async def test_recognize_with_vlm_with_executor(mock_vlm, mock_executor):
    """测试使用线程池异步调用 VLM"""
    recognizer = MediaRecognizer(mock_vlm, timeout=3.0, executor=mock_executor)

    async def fake_executor(executor, func, *args):
        return func(*args)

    with patch('asyncio.get_running_loop') as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=fake_executor)

        result = await recognizer._recognize_with_vlm("描述", ["/tmp/img.jpg"])

    assert result == "这是一张图片"


def test_is_vlm_available_true(media_recognizer, mock_vlm):
    """测试 VLM 可用"""
    assert media_recognizer._is_vlm_available() is True


def test_is_vlm_available_false():
    """测试 VLM 不可用"""
    recognizer = MediaRecognizer(None, timeout=3.0)
    assert recognizer._is_vlm_available() is False


def test_is_vlm_available_exception():
    """测试 VLM 检查抛出异常"""
    mock_vlm = Mock()
    mock_vlm._ensure_provider = Mock(side_effect=Exception("配置错误"))

    recognizer = MediaRecognizer(mock_vlm, timeout=3.0)
    assert recognizer._is_vlm_available() is False
