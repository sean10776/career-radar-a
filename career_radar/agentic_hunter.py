"""
Agentic Hunter Module
主動探測職缺平台（ATS）、具備 Filter 生成、深度分頁（Pagination）與關鍵字交叉檢索的自主代理引擎
"""

import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from .models import JobOpening
from .config import AppConfig, CrawlerConfig, MatchingConfig, CandidateConfig
from .llm_client import LocalLLMClient


class AgenticHunter:
    """
    自主式職缺探測代理人 (Agentic Career Hunter)
    不依賴死板的單頁靜態抓取，而是根據候選人畫像與目標公司 ATS 特徵：
    1. 自主規劃檢索意向（Keyword + Location Facets）
    2. 主動注入搜尋參數與過濾條件
    3. 自主深度翻頁探測（Deep Pagination Loop）
    4. 結構化聚合與去重評分
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        llm_client: Optional[LocalLLMClient] = None
    ):
        self.config = config or AppConfig()
        self.crawler_cfg = self.config.crawler
        self.matching_cfg = self.config.matching
        self.candidate_cfg = self.config.candidate
        self.llm = llm_client

        self.ctx = ssl.create_default_context()
        if not self.crawler_cfg.verify_ssl:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def hunt_company(
        self,
        company_id: str,
        company_name: str,
        job_site_url: str,
        max_pages: int = 3
    ) -> List[JobOpening]:
        """
        針對特定公司官方招募入口執行自主深度探測
        """
        url_lower = job_site_url.lower()
        jobs: List[JobOpening] = []

        # 1. Workday CXS API 深度分頁與過濾探測 (NVIDIA, Intel, Micron, NXP, Cadence, Marvell, Broadcom...)
        if "myworkdayjobs.com" in url_lower:
            jobs = self._hunt_workday(company_id, company_name, job_site_url, max_pages)

        # 2. Amazon Jobs API (AWS / Ring / Lab126)
        elif "amazon.jobs" in url_lower:
            jobs = self._hunt_amazon(company_id, company_name, job_site_url, max_pages)

        # 3. MediaTek 官方 tRPC 分頁探測
        elif "careers.mediatek.com" in url_lower:
            jobs = self._hunt_mediatek(company_id, company_name, job_site_url, max_pages)

        # 4. Garmin API 探測
        elif "garmin.com.tw" in url_lower:
            jobs = self._hunt_garmin(company_id, company_name, job_site_url)

        # 5. Qualcomm Sitemap 探測
        elif "qualcomm.com" in url_lower and "sitemap" in url_lower:
            jobs = self._hunt_qualcomm(company_id, company_name, job_site_url)

        # 6. 通用網站：若有 Local LLM 就緒，執行混合式分析；否則進行啟發式參數探索
        else:
            jobs = self._hunt_generic(company_id, company_name, job_site_url)

        # 統一評估契合度分數
        valid_jobs = []
        seen_ids = set()
        for j in jobs:
            if j.id in seen_ids or not j.title:
                continue
            seen_ids.add(j.id)
            j.evaluate_fit(self.matching_cfg)
            valid_jobs.append(j)

        # 依分數排序
        valid_jobs.sort(key=lambda x: x.match_score, reverse=True)
        return valid_jobs

    def _discover_workday_location_facets(self, cxs_url: str) -> Dict[str, List[str]]:
        """
        主動向 Workday 探測原生 Location Facets (如 Location_Country, locations, locationHierarchy1)
        自動比對 config.matching.target_locations (如 Taiwan, Taipei, Hsinchu)
        """
        applied: Dict[str, List[str]] = {}
        try:
            probe_payload = json.dumps({"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}).encode("utf-8")
            req = urllib.request.Request(
                cxs_url,
                data=probe_payload,
                headers={
                    "User-Agent": self.crawler_cfg.user_agent,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            target_locs = [l.lower() for l in self.matching_cfg.target_locations]

            for facet in data.get("facets", []):
                param = facet.get("facetParameter", "")
                matched_ids = []
                for val in facet.get("values", []):
                    desc = val.get("descriptor", "").lower()
                    if any(t in desc for t in target_locs):
                        fid = val.get("id")
                        if fid:
                            matched_ids.append(fid)
                if matched_ids and any(k in param.lower() for k in ["location", "country"]):
                    applied[param] = matched_ids
        except Exception:
            pass
        return applied

    def _hunt_workday(
        self,
        company_id: str,
        company_name: str,
        url: str,
        max_pages: int
    ) -> List[JobOpening]:
        """
        Workday 自主翻頁與 Filter 探測
        """
        results: List[JobOpening] = []
        seen_paths: Set[str] = set()

        try:
            parsed = urllib.parse.urlparse(url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            tenant = parsed.netloc.split(".")[0]
            site = parts[-1] if parts else "External"
            cxs_url = f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/jobs"

            # 1. 主動探測 Workday 原生 Location Filter (Facets)
            location_facets = self._discover_workday_location_facets(cxs_url)

            # 2. 構建探測查詢矩陣：若有原生 Location Filter 則鎖定台灣，否則回退文字查詢
            if location_facets:
                search_intents = [""] + self.matching_cfg.core_keywords[:4]
                applied_filter = location_facets
            else:
                search_intents = [f"Taiwan {kw}" for kw in self.matching_cfg.core_keywords[:4]] + self.matching_cfg.core_keywords[:3]
                applied_filter = {}

            for query in search_intents:
                offset = 0
                page_size = 20
                for page in range(max_pages):
                    payload = json.dumps({
                        "appliedFacets": applied_filter,
                        "limit": page_size,
                        "offset": offset,
                        "searchText": query
                    }).encode("utf-8")

                    req = urllib.request.Request(
                        cxs_url,
                        data=payload,
                        headers={
                            "User-Agent": self.crawler_cfg.user_agent,
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        }
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            total = data.get("total", 0)
                            postings = data.get("jobPostings", [])

                            if not postings:
                                break

                            for p in postings:
                                ext_path = p.get("externalPath")
                                if not ext_path or ext_path in seen_paths:
                                    continue
                                seen_paths.add(ext_path)

                                title = p.get("title", "").strip()
                                loc_text = p.get("locationsText", "Taiwan")
                                posted_on = p.get("postedOn", "")
                                full_url = f"https://{parsed.netloc}{ext_path}"
                                job_id = p.get("bulletFields", [ext_path.split("/")[-1]])[0] if p.get("bulletFields") else ext_path.split("/")[-1]

                                # 檢查地點是否符合目標（例如包含 Taiwan, Taipei, Hsinchu 或 remote）
                                is_target_loc = any(
                                    loc_kw.lower() in loc_text.lower()
                                    for loc_kw in self.matching_cfg.target_locations
                                )
                                # 若 query 本身帶有 Taiwan，通常已屬目標
                                if not is_target_loc and "taiwan" not in query.lower():
                                    continue

                                job = JobOpening(
                                    id=f"{company_id}_{job_id}",
                                    company_id=company_id,
                                    company_name=company_name,
                                    title=title,
                                    url=full_url,
                                    location=loc_text,
                                    published_date=posted_on,
                                    description=f"Workday Direct Headcount: {title} at {loc_text}"
                                )
                                results.append(job)

                            # 若已達到總數或最後一頁，終止該 query 的翻頁
                            if offset + page_size >= total:
                                break
                            offset += page_size

                    except Exception:
                        break

        except Exception:
            pass

        return results

    def _hunt_amazon(
        self,
        company_id: str,
        company_name: str,
        url: str,
        max_pages: int
    ) -> List[JobOpening]:
        """
        Amazon.jobs API 自主過濾與翻頁探測
        """
        results: List[JobOpening] = []
        seen_ids: Set[str] = set()

        search_terms = self.matching_cfg.core_keywords[:5] + ["Firmware", "Hardware"]
        search_terms = list(dict.fromkeys(search_terms))

        for query in search_terms:
            for page in range(max_pages):
                offset = page * 10
                api_url = (
                    f"https://www.amazon.jobs/en/search.json?"
                    f"country=TWN&base_query={urllib.parse.quote(query)}&offset={offset}&result_limit=10"
                )
                req = urllib.request.Request(
                    api_url,
                    headers={
                        "User-Agent": self.crawler_cfg.user_agent,
                        "Accept": "application/json"
                    }
                )
                try:
                    with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        hits = data.get("hits", 0)
                        jobs = data.get("jobs", [])

                        if not jobs:
                            break

                        for j in jobs:
                            jid = str(j.get("id_icims") or j.get("id") or "")
                            if not jid or jid in seen_ids:
                                continue
                            seen_ids.add(jid)

                            title = j.get("title", "").strip()
                            loc = f"{j.get('city_state_country') or j.get('location') or 'Taiwan'}"
                            posted = j.get("posted_date", "")
                            job_path = j.get("job_path", "")
                            full_url = f"https://www.amazon.jobs{job_path}" if job_path.startswith("/") else f"https://www.amazon.jobs/en/jobs/{jid}"

                            job = JobOpening(
                                id=f"{company_id}_{jid}",
                                company_id=company_id,
                                company_name=company_name,
                                title=title,
                                url=full_url,
                                location=loc,
                                published_date=posted,
                                description=j.get("description_short", "")
                            )
                            results.append(job)

                        if offset + 10 >= hits:
                            break
                except Exception:
                    break

        return results

    def _hunt_mediatek(
        self,
        company_id: str,
        company_name: str,
        url: str,
        max_pages: int
    ) -> List[JobOpening]:
        """
        聯發科 tRPC 翻頁探測
        """
        results: List[JobOpening] = []
        seen_ids: Set[str] = set()

        for page in range(1, max_pages + 1):
            try:
                payload = {
                    "0": {
                        "json": {
                            "page": page,
                            "limit": 25,
                            "sortBy": "publishedDate",
                            "order": "DESC",
                            "filters": {},
                            "jobQueryInfo": {
                                "keywords": self.matching_cfg.core_keywords[:5],
                                "relation": "OR"
                            },
                            "locales": "zh_TW"
                        }
                    }
                }
                query_str = urllib.parse.quote(json.dumps(payload))
                api_url = f"https://careers.mediatek.com/api/trpc/job.getJobs?batch=1&input={query_str}"
                req = urllib.request.Request(
                    api_url,
                    headers={
                        "User-Agent": self.crawler_cfg.user_agent,
                        "Referer": "https://careers.mediatek.com/zh-tw/jobs",
                        "Cookie": "NEXT_LOCALE=zh-tw"
                    }
                )
                with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    postings = data[0].get("result", {}).get("data", {}).get("json", {}).get("jobs", [])

                    if not postings:
                        break

                    for p in postings:
                        jid = str(p.get("id"))
                        if jid in seen_ids:
                            continue
                        seen_ids.add(jid)

                        title = p.get("title", "")
                        loc = p.get("properties", {}).get("location", {}).get("code", "台灣新竹/台北")
                        posted = (p.get("publishedDate") or "")[:10]
                        full_url = f"https://careers.mediatek.com/zh-tw/jobs/{jid}"

                        job = JobOpening(
                            id=f"{company_id}_{jid}",
                            company_id=company_id,
                            company_name=company_name,
                            title=title,
                            url=full_url,
                            location=loc,
                            published_date=posted,
                            description=f"MediaTek tRPC Opening: {title}"
                        )
                        results.append(job)
            except Exception:
                break

        return results

    def _hunt_garmin(
        self,
        company_id: str,
        company_name: str,
        url: str
    ) -> List[JobOpening]:
        """
        Garmin 台灣招募 API
        """
        results: List[JobOpening] = []
        try:
            api_url = "https://www.garmin.com.tw/_js/api_jobs?type=jobs&locale=zh_TW"
            req = urllib.request.Request(api_url, headers={"User-Agent": self.crawler_cfg.user_agent})
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for j in data.get("data", []):
                    title = j.get("jobName") or j.get("title") or ""
                    jid = str(j.get("id") or hash(title))
                    loc = j.get("city") or "Taiwan"
                    link = j.get("url") or f"https://www.garmin.com.tw/careers/job/{jid}"

                    job = JobOpening(
                        id=f"{company_id}_{jid}",
                        company_id=company_id,
                        company_name=company_name,
                        title=title,
                        url=link,
                        location=loc,
                        description=f"Category: {j.get('category')} | Salary: {j.get('salaryPeriod')}"
                    )
                    results.append(job)
        except Exception:
            pass
        return results

    def _hunt_qualcomm(
        self,
        company_id: str,
        company_name: str,
        sitemap_url: str
    ) -> List[JobOpening]:
        """
        Qualcomm Sitemap 探測
        """
        results: List[JobOpening] = []
        try:
            req = urllib.request.Request(sitemap_url, headers={"User-Agent": self.crawler_cfg.user_agent})
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            for url_elem in root.findall("sm:url", ns):
                loc = url_elem.find("sm:loc", ns)
                lastmod = url_elem.find("sm:lastmod", ns)
                if loc is not None and loc.text:
                    url_text = loc.text
                    t_lower = url_text.lower()
                    if any(l.lower() in t_lower for l in ["taiwan", "hsinchu", "taipei"]):
                        slug = url_text.split("/")[-1].split("?")[0]
                        clean_title = slug.replace("-", " ").title()
                        date_str = lastmod.text[:10] if lastmod is not None and lastmod.text else ""

                        job = JobOpening(
                            id=f"{company_id}_{slug}",
                            company_id=company_id,
                            company_name=company_name,
                            title=clean_title,
                            url=url_text,
                            location="Taiwan",
                            published_date=date_str,
                            description=f"Qualcomm Taiwan Opening: {clean_title}"
                        )
                        results.append(job)
        except Exception:
            pass
        return results

    def _hunt_generic(
        self,
        company_id: str,
        company_name: str,
        url: str
    ) -> List[JobOpening]:
        """
        通用招募網站探測：
        若是標準 HTML，抓取清洗後若有 Local LLM 則交由 LLM 解析；
        否則使用 Regex 啟發式抓取包含職缺資訊的連結
        """
        results: List[JobOpening] = []
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.crawler_cfg.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Cookie": "NEXT_LOCALE=zh-tw"
                }
            )
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                final_url = resp.geturl()
                html = resp.read().decode("utf-8", errors="ignore")

            # 若有 Local LLM Client 且已啟動
            if self.llm:
                clean_html = re.sub(r'<(script|style|svg|noscript|header|footer|nav)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
                clean_html = re.sub(r'<!--.*?-->', '', clean_html, flags=re.DOTALL)
                clean_html = re.sub(r'<(div|p|li|tr|h[1-6]|br)[^>]*>', '\n', clean_html, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', clean_html)
                text = re.sub(r'[ \t]+', ' ', text)
                text = re.sub(r'\n\s*\n', '\n', text).strip()

                if len(text) > 100:
                    llm_jobs = self.llm.parse_job_text(company_name, final_url, text[:self.crawler_cfg.max_text_chars])
                    for j in llm_jobs:
                        j.company_id = company_id
                        results.append(j)

        except Exception:
            pass

        return results
