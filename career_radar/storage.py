"""
Storage module for CareerRadar using JSON persistence
支援跨平台 (Windows/Linux/WSL) 與處理中暫存檔案於 tmp/ 目錄隔離維護
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from .models import JobOpening
from .config import StorageConfig
from .utils.platform_net import get_processing_temp_dir


class JobDatabase:
    def __init__(self, data_path: Optional[str] = None, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()

        # 處理中暫存目錄 (Linux: /tmp/career_radar_processing, Windows: %TEMP%\\career_radar_processing)
        self.processing_dir = get_processing_temp_dir(self.config.temp_subfolder)
        self.cache_lock_file = self.processing_dir / "processing.lock"

        if data_path:
            self.data_path = Path(data_path)
        else:
            # 預設儲存於當前工作目錄
            self.data_path = Path.cwd() / self.config.data_filename

        self._ensure_storage()

    def _ensure_storage(self):
        try:
            if not self.data_path.exists():
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump({"jobs": {}, "stats": {}, "updated_at": None}, f, ensure_ascii=False, indent=2)
        except OSError:
            # 唯讀沙盒環境自動降級至系統 tmp
            self.data_path = self.processing_dir / self.config.data_filename
            if not self.data_path.exists():
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump({"jobs": {}, "stats": {}, "updated_at": None}, f, ensure_ascii=False, indent=2)

    def _load_data(self) -> Dict:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            fallback = self.processing_dir / self.config.data_filename
            if fallback.exists():
                try:
                    with open(fallback, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return {"jobs": {}, "stats": {}, "updated_at": None}

    def _save_data(self, data: Dict):
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            self.data_path = self.processing_dir / self.config.data_filename
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def write_processing_marker(self, current_company: str, progress: str):
        """在 tmp/ 建立即時處理狀態標記檔"""
        marker_file = self.processing_dir / "current_task.json"
        try:
            with open(marker_file, "w", encoding="utf-8") as f:
                json.dump({
                    "current_company": current_company,
                    "progress": progress,
                    "timestamp": datetime.now().isoformat()
                }, f)
        except Exception:
            pass

    def clear_processing_marker(self):
        marker_file = self.processing_dir / "current_task.json"
        if marker_file.exists():
            try:
                marker_file.unlink()
            except Exception:
                pass

    def save_jobs(self, jobs: List[JobOpening]) -> Tuple[int, int]:
        data = self._load_data()
        stored_jobs = data.get("jobs", {})
        now_str = datetime.now().isoformat()
        new_count = 0
        updated_count = 0

        for job in jobs:
            job_key = job.id
            if job_key not in stored_jobs:
                job.is_new = True
                stored_jobs[job_key] = {
                    "id": job.id,
                    "company_id": job.company_id,
                    "company_name": job.company_name,
                    "title": job.title,
                    "url": job.url,
                    "location": job.location,
                    "published_date": job.published_date,
                    "first_seen": job.first_seen,
                    "last_seen": now_str,
                    "description": job.description,
                    "match_score": job.match_score,
                    "matched_keywords": job.matched_keywords,
                    "is_active": True
                }
                new_count += 1
            else:
                existing = stored_jobs[job_key]
                job.is_new = False
                job.first_seen = existing.get("first_seen", now_str)
                existing.update({
                    "title": job.title,
                    "url": job.url,
                    "location": job.location,
                    "published_date": job.published_date or existing.get("published_date"),
                    "last_seen": now_str,
                    "description": job.description or existing.get("description"),
                    "match_score": max(job.match_score, existing.get("match_score", 0)),
                    "matched_keywords": list(set(job.matched_keywords + existing.get("matched_keywords", []))),
                    "is_active": True
                })
                updated_count += 1

        data["jobs"] = stored_jobs
        data["updated_at"] = now_str
        self._save_data(data)
        return new_count, updated_count

    def get_matched_jobs(self, min_score: int = 20, limit: int = 150) -> List[JobOpening]:
        data = self._load_data()
        stored_jobs = data.get("jobs", {})
        result = []

        for j_dict in stored_jobs.values():
            if j_dict.get("is_active", True) and j_dict.get("match_score", 0) >= min_score:
                job = JobOpening(
                    id=j_dict["id"],
                    company_id=j_dict["company_id"],
                    company_name=j_dict["company_name"],
                    title=j_dict["title"],
                    url=j_dict["url"],
                    location=j_dict.get("location", ""),
                    published_date=j_dict.get("published_date"),
                    first_seen=j_dict.get("first_seen", ""),
                    last_seen=j_dict.get("last_seen", ""),
                    description=j_dict.get("description", ""),
                    match_score=j_dict.get("match_score", 0),
                    matched_keywords=j_dict.get("matched_keywords", [])
                )
                result.append(job)

        result.sort(key=lambda x: (x.published_date or "", x.match_score), reverse=True)
        return result[:limit]

    def get_stats(self) -> Dict[str, int]:
        data = self._load_data()
        stored_jobs = data.get("jobs", {})
        total = len(stored_jobs)
        high_match = sum(1 for j in stored_jobs.values() if j.get("match_score", 0) >= 40)
        companies = len(set(j.get("company_id") for j in stored_jobs.values()))
        return {
            "total_jobs": total,
            "high_match": high_match,
            "companies": companies,
        }
