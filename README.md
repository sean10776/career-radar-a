# 📡 CareerRadar (職缺雷達)

> **第一手科技與半導體職缺探勘雷達** ── 整合「自動反推招募官網」、「智慧底層 API/RSS 嗅探」與「本地 Local LLM (LM Studio / Ollama) 智慧萃取」。
> 
> *Zero-dependency, configuration-driven, cross-platform (Windows / Linux / WSL).*

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Obsidian Ready](https://img.shields.io/badge/Obsidian-Compatible-purple.svg)](https://obsidian.md/)

---

## 🌟 核心特色 (Key Features)

1. **自動反推官方 Job Site (Zero Per-Company Scraping)**：
   - 無需為個別公司維護爬蟲腳本。
   - 輸入任何公司名稱（如「聯發科」、「聯詠」、「NVIDIA」、「廣達」）或第三方職缺連結（104 / LinkedIn），自動反推其官方招募入口。
2. **現代 ATS 底層 API 與 RSS 嗅探**：
   - 自動檢測 `<link rel="alternate" ...>` RSS/Atom 訂閱介面。
   - 自動識別現代招募系統（Workday REST CXS、Garmin `api_jobs`、聯發科 tRPC、Qualcomm 即時 XML Sitemap 等），獲取剛開出 Headcount 的第一手數據，**比人力銀行與社群媒體聚合站早數天至數週**。
3. **Local LLM 結構化分析 (8GB VRAM 最佳化)**：
   - 支援 LM Studio 與 Ollama 本地運行，完全由本地模型解析網頁文本並計算契合度評分。
   - 特別針對 8GB VRAM 優化（如 `qwen3.8-4b-distill`），具備思考鏈（Reasoning）辨識能力，過濾非職缺雜訊，輸出嚴格 JSON 格式。
4. **完全配置驅動 (Zero Hardcode)**：
   - 個人專業背景、目標職能、關鍵字權重、LLM 端點、爬取參數與暫存路徑均由 `config.jsonc`（支援註解）管理，代碼內無任何寫死之個人資料或參數。
5. **跨平台與沙盒/暫存隔離 (Cross-Platform & Tmp Isolation)**：
   - 原生支援 **Windows (CMD / PowerShell)** 與 **Linux / WSL**。
   - WSL 環境下自動解析 Windows 宿主機 IP，免手動修改。
   - 處理中之暫存標記與快取檔案統一於系統 `tmp/` 目錄隔離管理。
6. **Obsidian 看板即時同步**：
   - 每次執行自動產生或更新 Markdown 視覺化看板，內建待辦 Checkbox（`- [ ]`）、契合度評分與官方直接應徵連結。

---

## 🏗️ 系統架構管線 (Architecture Pipeline)

```
[公司名稱 / 第三方 104 或 LinkedIn 連結]
                   │
                   ▼
[Stage 1: Job Site Resolver (自動反推招募站)]
  • 搜尋引擎反推與轉址追蹤，找出官方 Careers 專區
  • 檢測有無標準 RSS/Atom Feed
                   │
                   ▼
[Stage 2: Smart Extractor (底層 API / HTML 嗅探)]
  • 優先對接 Workday / tRPC / api_jobs / sitemap 原生數據流
  • 通用網頁去除 CSS、JS、導航等雜訊，產出純淨文字
                   │
                   ▼
[Stage 3: Local LLM Extraction (本地模型智慧萃取)]
  • 傳送至本地 LM Studio / Ollama (自動偵測 IP 與推薦模型)
  • 依據 config.jsonc 候選人畫像進行比對評分與 JSON 結構化
                   │
                   ▼
[Stage 4: JSON 儲存與 Obsidian 看板同步]
  • 儲存至 career_radar_data.json
  • 產生符合 Obsidian 格式的即時職缺看板筆記
```

---

## 🚀 快速上手 (Quick Start)

### 1. 複製專案與安裝
本專案基於 **Python 3.9+ 標準庫** 打造，**零外部 pip 套件依賴**：
```bash
git clone https://github.com/<your-username>/career-radar.git
cd career-radar
```

### 2. 建立自訂配置檔
```bash
# 自動從範本複製出 config.jsonc
python3 -m career_radar init-config
```
編輯 `config.jsonc`，設定您的專業背景、目標職缺角色、關鍵字加權、工作地點與 LLM 偏好。

### 3. 啟動 Local LLM (可選)
在 Windows 開啟 **LM Studio**（或在背景執行 **Ollama**）：
- 在 LM Studio 的 Developer / Server 分頁中啟動 Local Server（Port `1234`），並勾選 **"Serve on Local Network"**。
- 推薦載入模型（8GB VRAM 最佳化）：`qwen3.8-4b-distill` 或 `qwen3-8b`。

---

## 🛠️ CLI 常用指令

```bash
# 1. 查詢 LLM 連線狀態與模型推薦
python3 -m career_radar models

# 2. 掃描單一公司（支援中文名稱、英文名稱、或 104 網址）
python3 -m career_radar run --company "聯發科"
python3 -m career_radar run --company "NVIDIA"
python3 -m career_radar run --company "廣達"
python3 -m career_radar run --company "https://www.104.com.tw/company/b1f9w3c"

# 3. 按類別批次掃描
python3 -m career_radar run --category "Taiwan Top IC"
python3 -m career_radar run --category "Dream Foreign"

# 4. 單純測試反推某公司官方招募站與有無 RSS
python3 -m career_radar resolve "群聯電子"

# 5. 列出目標公司資料庫清單
python3 -m career_radar list-targets

# 6. 執行全自動單元測試
python3 -m unittest tests/test_suite.py
```

---

## ⚙️ 配置檔結構說明 (`config.jsonc`)

```jsonc
{
  "candidate": {
    "name": "Your Name",
    "years_of_experience": 5,
    "target_roles": ["Linux Kernel Engineer", "BSP Engineer", "Firmware Engineer"],
    "profile_summary": "個人技術亮點與經驗總結..."
  },
  "matching": {
    "core_keywords": ["Linux", "Kernel", "BSP", "Driver", "U-Boot", "Display"],
    "secondary_keywords": ["Firmware", "I2C", "SPI", "PCIe", "RTOS", "C/C++"],
    "exclude_keywords": ["Frontend", "Marketing", "Sales", "HR", "財務", "業務"],
    "target_locations": ["Taiwan", "Taipei", "Hsinchu", "Remote"]
  },
  "llm": {
    "enabled": true,
    "auto_detect_host": true, // WSL 環境自動偵測 Windows 宿主機 IP
    "endpoint": "http://127.0.0.1:1234/v1",
    "preferred_models": ["4b", "qwen3-8b", "7b"]
  },
  "storage": {
    "use_system_temp": true, // 處理中臨時檔案放置於 tmp/
    "data_filename": "career_radar_data.json",
    "dashboard_filename": "職缺雷達_即時監控看板.md"
  }
}
```

---

## 📄 開源授權 (License)

本專案採用 [MIT License](LICENSE) 授權。
