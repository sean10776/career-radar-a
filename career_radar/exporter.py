"""
Obsidian / Markdown Dashboard Exporter
依據配置檔動態輸出即時職缺雷達看板
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from .models import JobOpening
from .storage import JobDatabase
from .config import StorageConfig, MatchingConfig


class ObsidianExporter:
    def __init__(
        self,
        output_path: Optional[str] = None,
        storage_config: Optional[StorageConfig] = None,
        matching_config: Optional[MatchingConfig] = None
    ):
        self.storage_cfg = storage_config or StorageConfig()
        self.matching_cfg = matching_config or MatchingConfig()

        if output_path:
            self.output_path = Path(output_path)
        else:
            self.output_path = Path.cwd() / self.storage_cfg.dashboard_filename

    def export(self, db: JobDatabase, recent_scanned_jobs: List[JobOpening] = None):
        min_score = self.matching_cfg.min_score
        high_score = self.matching_cfg.high_match_score

        jobs = db.get_matched_jobs(min_score=min_score, limit=150)
        stats = db.get_stats()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_date = datetime.now().strftime("%Y-%m-%d")

        high_match_jobs = [j for j in jobs if j.match_score >= high_score]
        company_groups: Dict[str, List[JobOpening]] = {}
        for j in jobs:
            company_groups.setdefault(j.company_name, []).append(j)

        content = []
        content.append("---")
        content.append("title: 職缺雷達_即時監控看板 (Job Radar Dashboard)")
        content.append("tags:")
        content.append("  - career")
        content.append("  - job-radar")
        content.append("  - bsp")
        content.append("  - linux-kernel")
        content.append("  - auto-generated")
        content.append(f"updated: {today_date}")
        content.append("---")
        content.append("")
        content.append("# 📡 職缺雷達：第一手官網與 API 即時監控看板")
        content.append("")
        content.append("> [!TIP] 第一手情報優勢")
        content.append(f"> • **最後掃描時間**：`{now_str}`")
        content.append(f"> • **已監控公司數**：{stats['companies']} 家頂尖科技與半導體公司")
        content.append(f"> • **高契合職缺總數**：{len(high_match_jobs)} 檔核心職缺")
        content.append("> • **情報來源**：直接對接各公司內部 ATS API (Workday / tRPC / JSON / Sitemap)，**零延遲獲取剛開出的 Headcount**，早於 104 與 LinkedIn！")
        if self.storage_cfg.navigation_links:
            links_str = " ｜ ".join(self.storage_cfg.navigation_links)
            content.append(f"> • **關聯導航**：{links_str}")
        content.append("")

        content.append("## 🎯 核心高契合職缺推薦 (優先關注)")
        content.append("")
        content.append("| 狀態 | 公司 | 職缺職稱 (Job Title) | 地點 | 契合分 | 命中關鍵字 | 原始連結 |")
        content.append("| :---: | :--- | :--- | :--- | :---: | :--- | :--- |")

        for j in high_match_jobs[:40]:
            kw_str = "、".join(j.matched_keywords[:4]) if j.matched_keywords else "-"
            title_clean = j.title.replace("|", "/")
            content.append(f"| - [ ] | **{j.company_name}** | [{title_clean}]({j.url}) | {j.location} | `{j.match_score}` | `{kw_str}` | [官方直接應徵]({j.url}) |")

        content.append("")
        content.append("## 🏢 各大目標公司即時庫存分佈")
        content.append("")
        for comp_name, comp_jobs in sorted(company_groups.items()):
            content.append(f"### {comp_name} ({len(comp_jobs)} 筆職缺)")
            content.append("")
            for j in comp_jobs[:10]:
                date_str = f" `{j.published_date}`" if j.published_date else ""
                kw_str = f" · 關鍵字: `{','.join(j.matched_keywords[:3])}`" if j.matched_keywords else ""
                content.append(f"- - [ ] [{j.title}]({j.url}) ({j.location}){date_str}{kw_str}")
            if len(comp_jobs) > 10:
                content.append(f"- *...另有 {len(comp_jobs) - 10} 筆職缺已記錄在資料庫中*")
            content.append("")

        content.append("---")
        content.append("## 🛠️ 工具操作與自動更新指令")
        content.append("")
        content.append("- **即時重新掃描所有公司**：")
        content.append("  ```bash")
        content.append("  python3 -m career_radar run --category 'Taiwan Top IC'")
        content.append("  ```")
        content.append("- **指定單一公司掃描**：")
        content.append("  ```bash")
        content.append("  python3 -m career_radar run --company '瑞昱'")
        content.append("  ```")
        content.append("- **探勘新公司 Career 頁面有無 RSS / API 接口**：")
        content.append("  ```bash")
        content.append("  python3 -m career_radar resolve '群聯電子'")
        content.append("  ```")
        content.append("")

        output_text = "\n".join(content)
        try:
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(output_text)
        except OSError:
            # 沙盒唯讀環境自動降級至系統 tmp
            fallback_dir = Path(db.processing_dir)
            self.output_path = fallback_dir / self.storage_cfg.dashboard_filename
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(output_text)
