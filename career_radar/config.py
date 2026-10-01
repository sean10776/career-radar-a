"""
Configuration Loader Module
支援從 JSON / JSONC (含註解) 檔案載入所有系統與模型參數，杜絕程式碼 Hardcode
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .utils.jsonc import load_jsonc_file, parse_jsonc


@dataclass
class CandidateConfig:
    name: str = "Candidate"
    years_of_experience: int = 3
    target_roles: List[str] = field(default_factory=lambda: [
        "Embedded Software Engineer", "Firmware Engineer", "Linux Kernel Engineer", "BSP Engineer"
    ])
    profile_summary: str = (
        "具備嵌入式系統開發、Linux 驅動程式、SoC Bring-up、RTOS 與底層韌體開發實戰經驗。"
    )


@dataclass
class MatchingConfig:
    core_keywords: List[str] = field(default_factory=lambda: [
        "Linux", "Kernel", "BSP", "Device Driver", "Driver", "Bootloader", "U-Boot", "Display", "DTS", "Bring-up"
    ])
    secondary_keywords: List[str] = field(default_factory=lambda: [
        "Firmware", "FW", "Embedded", "SoC", "I2C", "SPI", "UART", "PCIe", "DMA", "RTOS", "ARM", "C/C++"
    ])
    exclude_keywords: List[str] = field(default_factory=lambda: [
        "Frontend", "UI/UX", "Marketing", "Sales", "Accountant", "HR", "會計", "業務", "行銷", "人資"
    ])
    target_locations: List[str] = field(default_factory=lambda: [
        "Taiwan", "Taipei", "Hsinchu", "Zhubei", "New Taipei", "Xizhi", "Taoyuan", "台灣", "台北", "新竹", "Remote"
    ])
    weights: Dict[str, int] = field(default_factory=lambda: {
        "core_title": 40,
        "core_body": 20,
        "secondary_title": 20,
        "secondary_body": 10,
        "location_bonus": 15
    })
    min_score: int = 20
    high_match_score: int = 45


@dataclass
class LLMConfig:
    enabled: bool = True
    auto_detect_host: bool = True
    endpoint: str = "http://127.0.0.1:1234/v1"
    port: int = 1234
    preferred_models: List[str] = field(default_factory=lambda: ["4b", "qwen3-8b", "7b", "8b", "9b"])
    temperature: float = 0.1
    max_tokens: int = 2500
    timeout_seconds: int = 45
    probe_timeout_seconds: float = 1.5


@dataclass
class StorageConfig:
    use_system_temp: bool = True
    temp_subfolder: str = "career_radar_processing"
    data_filename: str = "career_radar_data.json"
    dashboard_filename: str = "職缺雷達_即時監控看板.md"
    navigation_links: List[str] = field(default_factory=list)


@dataclass
class CrawlerConfig:
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    request_timeout_seconds: int = 12
    max_text_chars: int = 8000
    verify_ssl: bool = True


@dataclass
class AppConfig:
    candidate: CandidateConfig = field(default_factory=CandidateConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "AppConfig":
        """
        載入配置檔，優先尋找順序：
        1. 傳入之自訂路徑
        2. 當前工作目錄之 config.jsonc 或 config.json
        3. 專案根目錄之 config.example.jsonc
        4. 若皆無則使用預設值
        """
        paths_to_check = []
        if config_path:
            paths_to_check.append(Path(config_path))
        cwd = Path.cwd()
        paths_to_check.extend([
            cwd / "config.jsonc",
            cwd / "config.json",
            Path(__file__).parent.parent / "config.jsonc",
            Path(__file__).parent.parent / "config.example.jsonc",
        ])

        target_file = None
        for p in paths_to_check:
            if p.exists() and p.is_file():
                target_file = p
                break

        if not target_file:
            return cls()

        try:
            raw_data = load_jsonc_file(str(target_file))
            return cls.from_dict(raw_data)
        except Exception as e:
            # 容錯：若解析出錯則返回預設值
            return cls()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        cfg = cls()
        if "candidate" in data:
            c = data["candidate"]
            cfg.candidate = CandidateConfig(
                name=c.get("name", cfg.candidate.name),
                years_of_experience=c.get("years_of_experience", cfg.candidate.years_of_experience),
                target_roles=c.get("target_roles", cfg.candidate.target_roles),
                profile_summary=c.get("profile_summary", cfg.candidate.profile_summary),
            )
        if "matching" in data:
            m = data["matching"]
            cfg.matching = MatchingConfig(
                core_keywords=m.get("core_keywords", cfg.matching.core_keywords),
                secondary_keywords=m.get("secondary_keywords", cfg.matching.secondary_keywords),
                exclude_keywords=m.get("exclude_keywords", cfg.matching.exclude_keywords),
                target_locations=m.get("target_locations", cfg.matching.target_locations),
                weights=m.get("weights", cfg.matching.weights),
                min_score=m.get("min_score", cfg.matching.min_score),
                high_match_score=m.get("high_match_score", cfg.matching.high_match_score),
            )
        if "llm" in data:
            l_data = data["llm"]
            cfg.llm = LLMConfig(
                enabled=l_data.get("enabled", cfg.llm.enabled),
                auto_detect_host=l_data.get("auto_detect_host", cfg.llm.auto_detect_host),
                endpoint=l_data.get("endpoint", cfg.llm.endpoint),
                port=l_data.get("port", cfg.llm.port),
                preferred_models=l_data.get("preferred_models", cfg.llm.preferred_models),
                temperature=l_data.get("temperature", cfg.llm.temperature),
                max_tokens=l_data.get("max_tokens", cfg.llm.max_tokens),
                timeout_seconds=l_data.get("timeout_seconds", cfg.llm.timeout_seconds),
                probe_timeout_seconds=l_data.get("probe_timeout_seconds", cfg.llm.probe_timeout_seconds),
            )
        if "storage" in data:
            s = data["storage"]
            cfg.storage = StorageConfig(
                use_system_temp=s.get("use_system_temp", cfg.storage.use_system_temp),
                temp_subfolder=s.get("temp_subfolder", cfg.storage.temp_subfolder),
                data_filename=s.get("data_filename", cfg.storage.data_filename),
                dashboard_filename=s.get("dashboard_filename", cfg.storage.dashboard_filename),
                navigation_links=s.get("navigation_links", cfg.storage.navigation_links),
            )
        if "crawler" in data:
            cr = data["crawler"]
            cfg.crawler = CrawlerConfig(
                user_agent=cr.get("user_agent", cfg.crawler.user_agent),
                request_timeout_seconds=cr.get("request_timeout_seconds", cfg.crawler.request_timeout_seconds),
                max_text_chars=cr.get("max_text_chars", cfg.crawler.max_text_chars),
                verify_ssl=cr.get("verify_ssl", cfg.crawler.verify_ssl),
            )
        return cfg


def load_target_companies(targets_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    載入目標公司目錄 targets.jsonc 或 targets.json
    """
    paths = []
    if targets_path:
        paths.append(Path(targets_path))
    cwd = Path.cwd()
    paths.extend([
        cwd / "targets.jsonc",
        cwd / "targets.json",
        Path(__file__).parent.parent / "targets.jsonc",
        Path(__file__).parent.parent / "targets.json",
    ])

    for p in paths:
        if p.exists() and p.is_file():
            try:
                return load_jsonc_file(str(p))
            except Exception:
                pass
    return []
