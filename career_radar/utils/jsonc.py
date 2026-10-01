"""
JSONC (JSON with Comments) Parser
支援單行註解 (//)、多行註解 (/* */) 與結尾逗號 (trailing commas)
純標準庫實作，零外部依賴
"""

import json
import re
from typing import Any


def parse_jsonc(text: str) -> Any:
    """
    解析帶有註解的 JSONC 字串為 Python 資料結構
    """
    # 正則表達式：匹配字串（保留內容）或註解（移除）
    pattern = r'(\"(?:\\.|[^"\\])*\")|(/\*[\s\S]*?\*/|//[^\n]*)'

    def replacer(match):
        if match.group(1):
            return match.group(1)  # 保留字串字面量
        return ""  # 移除註解

    cleaned = re.sub(pattern, replacer, text)
    # 移除物件或陣列中最後多餘的逗號 (Trailing Commas)
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    return json.loads(cleaned)


def load_jsonc_file(file_path: str) -> Any:
    """
    從檔案路徑載入並解析 JSONC 檔案
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return parse_jsonc(f.read())
