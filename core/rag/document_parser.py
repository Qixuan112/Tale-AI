"""
文档解析器
支持 txt / md / pdf / csv 格式
"""

from pathlib import Path
from typing import List


class DocumentParser:
    """解析上传的文档为纯文本"""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".csv"}

    def parse(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower().lstrip(".")
        handler = {
            "txt": self._parse_text,
            "md": self._parse_text,
            "pdf": self._parse_pdf,
            "csv": self._parse_csv,
        }.get(ext)
        if handler is None:
            raise ValueError(f"不支持的文件类型: .{ext}")
        return handler(file_path)

    def _parse_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _parse_pdf(self, path: str) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("解析 PDF 需要 pypdf 库: pip install pypdf")
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _parse_csv(self, path: str) -> str:
        import csv
        rows = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f):
                rows.append(" | ".join(row))
        return "\n".join(rows)
