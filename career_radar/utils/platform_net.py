"""
Cross-Platform Environment and Network Utilities
支援 Windows, Linux 與 WSL 環境之宿主機 IP 與暫存目錄自動解析
"""

import sys
import os
import socket
import tempfile
from pathlib import Path


def detect_platform() -> str:
    """
    偵測目前執行環境: 'windows', 'wsl', 或 'linux' (含 macOS)
    """
    if sys.platform == "win32":
        return "windows"
    if os.path.exists("/proc/version"):
        try:
            with open("/proc/version", "r", encoding="utf-8") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except Exception:
            pass
    return "linux"


def resolve_llm_host(configured_endpoint: str = "http://127.0.0.1:1234/v1", auto_detect: bool = True) -> str:
    """
    解析 Local LLM 端點：
    - 若在原生 Windows 或原生 Linux: 使用 127.0.0.1
    - 若在 WSL: 自動探查 Windows 宿主機閘道 IP (如 172.x.x.1)
    """
    if not auto_detect:
        return configured_endpoint

    plat = detect_platform()
    if plat != "wsl":
        return configured_endpoint

    # WSL 環境：解析 Windows 宿主機 IP
    gateway_ip = None

    # 1. 嘗試從 /proc/net/route 讀取預設閘道
    try:
        with open("/proc/net/route", "r") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    val = int(fields[2], 16)
                    gateway_ip = socket.inet_ntoa(val.to_bytes(4, "little"))
                    break
    except Exception:
        pass

    # 2. 嘗試從 /etc/resolv.conf 讀取 nameserver
    if not gateway_ip:
        try:
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        gateway_ip = line.split()[1]
                        break
        except Exception:
            pass

    if gateway_ip and gateway_ip != "127.0.0.1":
        # 替換 configured_endpoint 中的 host 為 gateway_ip
        # 例：http://127.0.0.1:1234/v1 -> http://172.x.x.1:1234/v1
        return configured_endpoint.replace("127.0.0.1", gateway_ip).replace("localhost", gateway_ip)

    return configured_endpoint


def get_processing_temp_dir(subfolder: str = "career_radar") -> Path:
    """
    取得符合當前作業系統規範的暫存處理目錄 (Linux/WSL: /tmp/..., Windows: %TEMP%/...)
    """
    base_tmp = Path(tempfile.gettempdir())
    target_dir = base_tmp / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir
