"""
测试 IDSanitizer 的打码和还原功能
"""
import pytest
from core.utils.id_sanitizer import IDSanitizer


def test_sanitize_user_id():
    """测试用户ID打码"""
    sanitizer = IDSanitizer()
    masked1 = sanitizer.sanitize_user_id("123456")
    masked2 = sanitizer.sanitize_user_id("123456")

    # 同一ID多次调用返回相同的打码ID
    assert masked1 == masked2
    assert masked1.startswith("usr_")

    # 还原功能正常
    assert sanitizer.restore_user_id(masked1) == "123456"


def test_sanitize_group_id():
    """测试群ID打码"""
    sanitizer = IDSanitizer()
    masked = sanitizer.sanitize_group_id("987654")

    assert masked.startswith("grp_")
    assert sanitizer.restore_group_id(masked) == "987654"


def test_different_ids_get_different_masks():
    """测试不同ID得到不同的打码"""
    sanitizer = IDSanitizer()
    masked1 = sanitizer.sanitize_user_id("111111")
    masked2 = sanitizer.sanitize_user_id("222222")

    assert masked1 != masked2
    assert sanitizer.restore_user_id(masked1) == "111111"
    assert sanitizer.restore_user_id(masked2) == "222222"


def test_restore_non_masked_id():
    """测试还原非打码ID时原样返回"""
    sanitizer = IDSanitizer()

    # 非打码ID原样返回
    assert sanitizer.restore_user_id("123456") == "123456"
    assert sanitizer.restore_group_id("987654") == "987654"


def test_empty_id_handling():
    """测试空ID的处理"""
    sanitizer = IDSanitizer()

    assert sanitizer.sanitize_user_id("") == ""
    assert sanitizer.sanitize_user_id(None) == ""
    assert sanitizer.sanitize_group_id("") == ""
    assert sanitizer.sanitize_group_id(None) == ""

    assert sanitizer.restore_user_id("") == ""
    assert sanitizer.restore_group_id("") == ""


def test_is_masked_id():
    """测试判断是否为打码ID"""
    sanitizer = IDSanitizer()

    masked_user = sanitizer.sanitize_user_id("123456")
    masked_group = sanitizer.sanitize_group_id("987654")

    assert sanitizer.is_masked_user_id(masked_user) is True
    assert sanitizer.is_masked_user_id("123456") is False
    assert sanitizer.is_masked_user_id("") is False

    assert sanitizer.is_masked_group_id(masked_group) is True
    assert sanitizer.is_masked_group_id("987654") is False
    assert sanitizer.is_masked_group_id("") is False


def test_numeric_id_conversion():
    """测试数字ID自动转字符串"""
    sanitizer = IDSanitizer()

    # 传入数字应该自动转换
    masked = sanitizer.sanitize_user_id(123456)
    assert masked.startswith("usr_")
    assert sanitizer.restore_user_id(masked) == "123456"


def test_counter_increment():
    """测试计数器递增，确保唯一性"""
    sanitizer = IDSanitizer()

    masked1 = sanitizer.sanitize_user_id("111")
    masked2 = sanitizer.sanitize_user_id("222")
    masked3 = sanitizer.sanitize_group_id("333")

    # 提取计数器部分
    counter1 = int(masked1.split("_")[1])
    counter2 = int(masked2.split("_")[1])
    counter3 = int(masked3.split("_")[1])

    # 计数器应该递增
    assert counter2 == counter1 + 1
    assert counter3 == counter2 + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
