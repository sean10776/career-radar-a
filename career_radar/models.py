"""
Data models for CareerRadar
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import re
from .config import MatchingConfig


@dataclass
class JobOpening:
    id: str
    company_id: str
    company_name: str
    title: str
    url: str
    location: str
    published_date: Optional[str] = None
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    description: str = ""
    match_score: int = 0
    matched_keywords: List[str] = field(default_factory=list)
    is_new: bool = False

    def evaluate_fit(self, config: Optional[MatchingConfig] = None) -> int:
        """
        評估該職缺與候選人經歷的契合度分數 (參數完全由 config.jsonc 驅動，無任何 Hardcode)
        """
        if config is None:
            config = MatchingConfig()

        text = f"{self.title} {self.description} {self.location}".lower()

        # 1. 檢查排除關鍵字
        for ex in config.exclude_keywords:
            ex_lower = ex.lower()
            if re.search(r'\b' + re.escape(ex_lower) + r'\b', text, re.IGNORECASE) or (len(ex_lower) <= 4 and ex_lower in text):
                # 若包含核心關鍵字則酌情保留，否則分數歸零
                if not any(k.lower() in self.title.lower() for k in config.core_keywords):
                    self.match_score = 0
                    self.matched_keywords = []
                    return 0

        score = 0
        matched = []
        weights = config.weights

        # 2. 核心關鍵字評分
        for core in config.core_keywords:
            pattern = r'(?:\b|_)' + re.escape(core.lower()) + r'(?:\b|_)'
            if re.search(pattern, text) or core.lower() in self.title.lower():
                if core.lower() in self.title.lower():
                    score += weights.get("core_title", 40)
                else:
                    score += weights.get("core_body", 20)
                if core not in matched:
                    matched.append(core)

        # 3. 輔助關鍵字評分
        for sec in config.secondary_keywords:
            pattern = r'(?:\b|_)' + re.escape(sec.lower()) + r'(?:\b|_)'
            if re.search(pattern, text) or sec.lower() in self.title.lower():
                if sec.lower() in self.title.lower():
                    score += weights.get("secondary_title", 20)
                else:
                    score += weights.get("secondary_body", 10)
                if sec not in matched:
                    matched.append(sec)

        # 4. 地點加分
        loc_match = any(loc.lower() in text for loc in config.target_locations)
        if loc_match:
            score += weights.get("location_bonus", 15)

        self.match_score = score
        self.matched_keywords = matched
        return score
