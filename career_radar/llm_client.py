"""
Local LLM Client for LM Studio / Ollama
完全由 JSONC 配置驅動，支援 Windows, Linux 與 WSL 自動宿主機 IP 解析
"""

import urllib.request
import json
import re
from typing import List, Dict, Any, Optional
from .models import JobOpening
from .config import LLMConfig, CandidateConfig
from .utils.platform_net import resolve_llm_host


class LocalLLMClient:
    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        candidate_config: Optional[CandidateConfig] = None,
        override_endpoint: Optional[str] = None,
        override_model: Optional[str] = None,
    ):
        self.llm_cfg = llm_config or LLMConfig()
        self.candidate_cfg = candidate_config or CandidateConfig()

        # 解析端點 (支援跨平台與 WSL 自動偵測)
        base_endpoint = override_endpoint or self.llm_cfg.endpoint
        self.endpoint = resolve_llm_host(base_endpoint, self.llm_cfg.auto_detect_host).rstrip("/")
        self.model = override_model
        self.is_connected = None

    def check_connection(self) -> bool:
        """快速探測 LLM 服務是否正常就緒"""
        url = f"{self.endpoint}/models"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerRadar/1.0"})
            with urllib.request.urlopen(req, timeout=self.llm_cfg.probe_timeout_seconds) as resp:
                self.is_connected = (resp.status == 200)
                return self.is_connected
        except Exception:
            self.is_connected = False
            return False

    def get_models(self) -> List[str]:
        """向伺服器查詢目前已下載或就緒的模型清單"""
        url = f"{self.endpoint}/models"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerRadar/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return models
        except Exception:
            return []

    def get_recommended_model(self) -> Optional[str]:
        """依據配置檔中的 preferred_models 順序自動推薦最適模型"""
        models = self.get_models()
        if not models:
            return None

        for pref in self.llm_cfg.preferred_models:
            for m in models:
                if pref.lower() in m.lower():
                    return m
        return models[0]

    def _build_system_prompt(self) -> str:
        """動態生成提示詞 (依據 candidate 配置無任何 Hardcode)"""
        roles_str = "、".join(self.candidate_cfg.target_roles)
        return (
            f"你是一位頂尖半導體與高科技求職顧問。候選人擁有 {self.candidate_cfg.years_of_experience} 年以上實戰經驗，"
            f"目標職缺類別包含：{roles_str}。\n"
            f"專業背景簡介：{self.candidate_cfg.profile_summary}\n\n"
            "請從以下公司招募網頁文本中，找出所有符合或契合該候選人背景的工程師職缺。"
            "排除純業務、財務、人資、純前端網頁與非技術職缺。\n"
            "請務必輸出純 JSON 陣列 (JSON Array)，不要有任何額外的解釋文字或 Markdown 開頭，格式範例如下：\n"
            "[\n"
            "  {\n"
            '    "title": "職缺名稱",\n'
            '    "location": "工作地點",\n'
            '    "keywords": ["命中技術關鍵字"],\n'
            '    "match_score": 85,\n'
            '    "summary": "15字以內技術說明"\n'
            "  }\n"
            "]"
        )

    def parse_job_text(self, company_name: str, site_url: str, raw_text: str) -> List[JobOpening]:
        """將網頁文本送交 Local LLM 抽取結構化職缺"""
        if not raw_text.strip():
            return []

        if self.is_connected is None:
            self.check_connection()

        if not self.is_connected:
            return self._heuristic_fallback(company_name, site_url, raw_text)

        active_model = self.model or self.get_recommended_model()
        system_prompt = self._build_system_prompt()
        user_prompt = f"【目標公司】：{company_name}\n【網頁文本內容】：\n{raw_text[:7000]}"

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": self.llm_cfg.temperature,
            "max_tokens": self.llm_cfg.max_tokens,
            "stream": False
        }
        if active_model:
            payload["model"] = active_model

        req_data = json.dumps(payload).encode("utf-8")
        url = f"{self.endpoint}/chat/completions"
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CareerRadar/1.0"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.llm_cfg.timeout_seconds) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                choice = resp_json.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "").strip()

                if not content and "reasoning_content" in msg:
                    content = msg.get("reasoning_content", "")

                if "```json" in content:
                    content = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL).group(1)
                elif "```" in content:
                    m = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
                    if m:
                        content = m.group(1)

                json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

                parsed_items = json.loads(content)
                if not isinstance(parsed_items, list):
                    parsed_items = [parsed_items]

                jobs = []
                for item in parsed_items:
                    title = item.get("title", "")
                    if not title:
                        continue
                    loc = item.get("location", "Taiwan")
                    score = item.get("match_score", 50)
                    kw = item.get("keywords", [])
                    desc = item.get("summary", "")

                    job_id = f"{company_name}:{re.sub(r'[^a-zA-Z0-9]', '_', title)}"
                    job = JobOpening(
                        id=job_id,
                        company_id=company_name.lower().replace(" ", "_"),
                        company_name=company_name,
                        title=title,
                        url=site_url,
                        location=loc,
                        description=desc,
                        match_score=score,
                        matched_keywords=kw
                    )
                    jobs.append(job)
                return jobs

        except Exception:
            return self._heuristic_fallback(company_name, site_url, raw_text)

    def _heuristic_fallback(self, company_name: str, site_url: str, raw_text: str) -> List[JobOpening]:
        """啟發式保底解析引擎"""
        jobs = []
        lines = raw_text.split('\n')
        seen_titles = set()

        for line in lines:
            line_str = line.strip()
            if len(line_str) < 5 or len(line_str) > 80:
                continue

            is_job = any(k in line_str.lower() for k in ["engineer", "developer", "工程師", "架構師", "bsp", "firmware", "driver", "kernel", "linux"])
            not_irrelevant = not any(k in line_str.lower() for k in ["sales", "accounting", "hr", "行政", "業務", "財務"])

            if is_job and not_irrelevant:
                if line_str not in seen_titles:
                    seen_titles.add(line_str)
                    clean_title = line_str
                    m_title = re.search(r'(?:職缺|職缺名稱):\s*([^,，]+)', clean_title)
                    if m_title:
                        clean_title = m_title.group(1).strip()
                    else:
                        clean_title = re.sub(r'^-\s*', '', clean_title).split(',')[0].strip()

                    job_id = f"{company_name}:{re.sub(r'[^a-zA-Z0-9]', '_', clean_title)}"
                    job = JobOpening(
                        id=job_id,
                        company_id=company_name.lower().replace(" ", "_"),
                        company_name=company_name,
                        title=clean_title,
                        url=site_url,
                        location="Taiwan",
                        description=line_str
                    )
                    job.evaluate_fit()
                    if job.match_score > 0:
                        jobs.append(job)

        return jobs[:10]
