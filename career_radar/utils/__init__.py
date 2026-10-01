"""
Utility modules for CareerRadar
"""

from .jsonc import parse_jsonc, load_jsonc_file
from .platform_net import detect_platform, resolve_llm_host, get_processing_temp_dir

__all__ = [
    "parse_jsonc",
    "load_jsonc_file",
    "detect_platform",
    "resolve_llm_host",
    "get_processing_temp_dir",
]
