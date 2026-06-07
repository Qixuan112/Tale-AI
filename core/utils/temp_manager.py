"""
临时文件管理器
===============
管理 data/temp/ 目录中的图片文件，自动清理超量/过期文件。
"""

import time
from pathlib import Path


class TempFileManager:
    """管理临时图片文件，自动清理。"""

    TEMP_DIR = Path("data/temp")
    MAX_SIZE_MB = 100
    MAX_FILE_AGE_HOURS = 24

    def __init__(self):
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def save_image(self, image_data: bytes, filename: str = None) -> str:
        """保存图片到 temp 目录，返回相对路径。"""
        if filename is None:
            filename = f"upload_{int(time.time() * 1000)}.png"
        filepath = self.TEMP_DIR / filename
        filepath.write_bytes(image_data)
        self.cleanup()
        return str(filepath)

    def cleanup(self):
        """清理过期/超量文件。"""
        now = time.time()
        max_bytes = self.MAX_SIZE_MB * 1024 * 1024
        max_age_sec = self.MAX_FILE_AGE_HOURS * 3600

        if not self.TEMP_DIR.exists():
            return
        files = list(self.TEMP_DIR.iterdir())
        if not files:
            return

        files.sort(key=lambda f: f.stat().st_mtime)

        for f in files:
            try:
                if now - f.stat().st_mtime > max_age_sec:
                    f.unlink()
            except OSError:
                pass

        remaining = [f for f in files if f.exists()]
        remaining.sort(key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in remaining)
        for f in remaining:
            if total <= max_bytes:
                break
            try:
                total -= f.stat().st_size
                f.unlink()
            except OSError:
                pass

    def get_total_size(self) -> int:
        if not self.TEMP_DIR.exists():
            return 0
        return sum(f.stat().st_size for f in self.TEMP_DIR.iterdir() if f.is_file())


temp_manager = TempFileManager()
