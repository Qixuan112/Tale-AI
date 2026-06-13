"""
文本分块器
按段落分块 + 重叠窗口策略
"""

from typing import List


class TextChunker:
    """段落级文本分块，支持重叠窗口"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> List[str]:
        """将文本按段落分块"""
        import re
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return self._merge_paragraphs(paragraphs)

    def _merge_paragraphs(self, paragraphs: List[str]) -> List[str]:
        chunks = []
        current = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            # 如果单个段落超过 chunk_size，需要拆分
            if para_len > self.chunk_size:
                # 先提交当前累积的段落
                if current:
                    chunks.append("\n\n".join(current))
                # 将超大段落按 chunk_size 拆分
                start = 0
                while start < para_len:
                    end = min(start + self.chunk_size, para_len)
                    slice_text = para[start:end]
                    if start > 0:
                        # 重叠前一 slice 的尾部
                        overlap_start = max(0, start - self.overlap)
                        if overlap_start < start:
                            slice_text = para[overlap_start:end]
                    chunks.append(slice_text)
                    start = end
                current = []
                current_len = 0
                continue

            if current_len + para_len <= self.chunk_size:
                current.append(para)
                current_len += para_len
            else:
                if current:
                    chunks.append("\n\n".join(current))
                overlap_text = self._get_overlap(current, self.overlap)
                current = [overlap_text, para] if overlap_text else [para]
                current_len = len(overlap_text) + para_len if overlap_text else para_len

        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _get_overlap(self, paragraphs: List[str], overlap_chars: int) -> str:
        if not paragraphs or overlap_chars <= 0:
            return ""
        combined = "\n\n".join(paragraphs)
        return combined[-overlap_chars:] if len(combined) > overlap_chars else ""
