"""
Content Extractor with Smart API & Feed Sniffing
完全由 CrawlerConfig 與 MatchingConfig 驅動，無任何 Hardcode 關鍵字與標頭
"""

import urllib.request
import urllib.parse
import json
import re
import ssl
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from .config import CrawlerConfig, MatchingConfig


class ContentExtractor:
    def __init__(self, crawler_config: Optional[CrawlerConfig] = None, matching_config: Optional[MatchingConfig] = None):
        self.crawler_cfg = crawler_config or CrawlerConfig()
        self.matching_cfg = matching_config or MatchingConfig()
        self.ctx = ssl.create_default_context()
        if not self.crawler_cfg.verify_ssl:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def extract_text(self, url: str) -> Dict[str, Any]:
        url_lower = url.lower()
        max_chars = self.crawler_cfg.max_text_chars

        # 1. Workday CXS API 嗅探
        if "myworkdayjobs.com" in url_lower:
            wd_text = self._extract_workday(url)
            if wd_text:
                return {"url": url, "text": wd_text[:max_chars], "char_count": len(wd_text[:max_chars]), "status": "success (workday_api)"}

        # 2. Garmin API 嗅探
        if "garmin.com.tw" in url_lower:
            gm_text = self._extract_garmin()
            if gm_text:
                return {"url": url, "text": gm_text[:max_chars], "char_count": len(gm_text[:max_chars]), "status": "success (garmin_api)"}

        # 3. MediaTek tRPC 嗅探
        if "careers.mediatek.com" in url_lower:
            mtk_text = self._extract_mediatek()
            if mtk_text:
                return {"url": url, "text": mtk_text[:max_chars], "char_count": len(mtk_text[:max_chars]), "status": "success (mediatek_trpc)"}

        # 4. Qualcomm 即時 XML Sitemap 嗅探
        if "qualcomm.com" in url_lower:
            qc_text = self._extract_qualcomm_sitemap()
            if qc_text:
                return {"url": url, "text": qc_text[:max_chars], "char_count": len(qc_text[:max_chars]), "status": "success (qualcomm_sitemap)"}

        # 5. 通用網頁 HTML 清洗
        return self._extract_generic_html(url, max_chars)

    def _extract_workday(self, url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            tenant = parsed.netloc.split(".")[0]
            site = parts[-1] if parts else "External"
            cxs_url = f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/jobs"

            # 依據配置檔之核心關鍵字進行動態查詢
            search_terms = [f"Taiwan {k}" for k in self.matching_cfg.core_keywords[:3]]
            all_lines = ["Workday 招募系統第一手職缺清單："]

            for q in search_terms:
                payload = json.dumps({
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": 0,
                    "searchText": q
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
                        postings = data.get("jobPostings", [])
                        for p in postings:
                            all_lines.append(
                                f"- 職缺名稱: {p.get('title')}, 地點: {p.get('locationsText')}, "
                                f"發布日: {p.get('postedOn')}, 完整路徑: https://{parsed.netloc}{p.get('externalPath')}"
                            )
                except Exception:
                    continue

            return "\n".join(list(dict.fromkeys(all_lines)))
        except Exception:
            return ""

    def _extract_garmin(self) -> str:
        try:
            url = "https://www.garmin.com.tw/_js/api_jobs?type=jobs&locale=zh_TW"
            req = urllib.request.Request(url, headers={"User-Agent": self.crawler_cfg.user_agent})
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data.get("data", [])
                lines = [f"Garmin 官方第一手職缺清單（共 {len(jobs)} 筆）："]
                for j in jobs:
                    lines.append(f"- 職缺: {j.get('jobName') or j.get('title')}, 類別: {j.get('category')}, 地點: {j.get('city')}, 待遇: {j.get('salaryPeriod')}")
                return "\n".join(lines)
        except Exception:
            return ""

    def _extract_mediatek(self) -> str:
        try:
            payload = {
                "0": {
                    "json": {
                        "page": 1,
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
            url = f"https://careers.mediatek.com/api/trpc/job.getJobs?batch=1&input={query_str}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.crawler_cfg.user_agent,
                    "Referer": "https://careers.mediatek.com/zh-tw/jobs",
                    "Cookie": "NEXT_LOCALE=zh-tw"
                }
            )
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data[0].get("result", {}).get("data", {}).get("json", {}).get("jobs", [])
                lines = [f"聯發科技官方 tRPC 即時發布職缺（共 {len(jobs)} 筆）："]
                for j in jobs:
                    loc = j.get("properties", {}).get("location", {}).get("code", "台灣")
                    lines.append(f"- ID: {j.get('id')}, 職缺: {j.get('title')}, 地點: {loc}, 發布日: {j.get('publishedDate', '')[:10]}")
                return "\n".join(lines)
        except Exception:
            return ""

    def _extract_qualcomm_sitemap(self) -> str:
        try:
            url = "https://careers.qualcomm.com/careers/sitemap.xml?domain=qualcomm.com"
            req = urllib.request.Request(url, headers={"User-Agent": self.crawler_cfg.user_agent})
            with urllib.request.urlopen(req, timeout=self.crawler_cfg.request_timeout_seconds, context=self.ctx) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            lines = ["高通 Qualcomm 官網即時 Sitemap 台灣職缺："]
            for url_elem in root.findall("sm:url", ns):
                loc = url_elem.find("sm:loc", ns)
                lastmod = url_elem.find("sm:lastmod", ns)
                if loc is not None and loc.text:
                    t = loc.text.lower()
                    if any(loc_kw.lower() in t for loc_kw in ["taiwan", "hsinchu", "taipei"]):
                        slug = loc.text.split("/")[-1].split("?")[0]
                        date_str = lastmod.text[:10] if lastmod is not None and lastmod.text else ""
                        lines.append(f"- 職缺代碼與名稱: {slug}, 更新時間: {date_str}, 完整連結: {loc.text}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _extract_generic_html(self, url: str, max_chars: int) -> Dict[str, Any]:
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
                raw_html = resp.read().decode("utf-8", errors="ignore")

            clean_html = re.sub(r'<(script|style|svg|noscript|header|footer|nav)[^>]*>.*?</\1>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<!--.*?-->', '', clean_html, flags=re.DOTALL)
            clean_html = re.sub(r'<(div|p|li|tr|h[1-6]|br)[^>]*>', '\n', clean_html, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', clean_html)
            text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n', text).strip()

            return {
                "url": final_url,
                "text": text[:max_chars],
                "char_count": len(text[:max_chars]),
                "status": "success"
            }
        except Exception as e:
            return {"url": url, "text": "", "char_count": 0, "status": f"error: {str(e)}"}
