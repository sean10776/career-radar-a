"""
Job Site Resolver
自動將目標公司名稱或第三方平台連結（104 / LinkedIn / 官網首頁）反推出真正的官方 Job Site 與 RSS Feed
"""

import urllib.request
import urllib.parse
import re
import ssl
from typing import Dict, Any, Optional
from .config import CrawlerConfig


class JobSiteResolver:
    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.config = config or CrawlerConfig()
        self.ctx = ssl.create_default_context()
        if not self.config.verify_ssl:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def resolve(self, company_name: str, hint_url: Optional[str] = None) -> Dict[str, Any]:
        result = {
            "company_name": company_name,
            "resolved_career_url": None,
            "has_rss": False,
            "rss_url": None,
            "ats_type": None,
            "candidates": []
        }

        # 若已有明確非第三方的官方提示連結
        if hint_url and not any(x in hint_url for x in ["104.com.tw", "linkedin.com", "1111.com.tw"]):
            result["resolved_career_url"] = hint_url
            self._inspect_career_url(hint_url, result)
            return result

        search_query = f"{company_name} 招募 OR career OR jobs 官網"
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"

        try:
            req = urllib.request.Request(ddg_url, headers={"User-Agent": self.config.user_agent})
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds, context=self.ctx) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            raw_links = re.findall(r'uddg=([^&]+)', html)
            cleaned_links = []
            exclude_domains = [
                "duckduckgo.com", "104.com.tw", "1111.com.tw", "yes123.com.tw",
                "cakeresume.com", "linkedin.com", "facebook.com", "youtube.com",
                "wikipedia.org", "instagram.com"
            ]

            for raw in raw_links:
                decoded = urllib.parse.unquote(raw)
                if not any(ex in decoded for ex in exclude_domains):
                    cleaned_links.append(decoded)

            primary_choice = None
            for link in cleaned_links:
                lower = link.lower()
                if any(k in lower for k in ["career", "recruit", "job", "join", "talent", "hire", "workday"]):
                    primary_choice = link
                    break

            if not primary_choice and cleaned_links:
                primary_choice = cleaned_links[0]

            result["resolved_career_url"] = primary_choice
            result["candidates"] = cleaned_links[:5]

            if primary_choice:
                self._inspect_career_url(primary_choice, result)

        except Exception as e:
            result["error"] = str(e)

        return result

    def _inspect_career_url(self, url: str, result: Dict[str, Any]):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.config.user_agent, "Cookie": "NEXT_LOCALE=zh-tw"}
            )
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds, context=self.ctx) as resp:
                final_url = resp.geturl()
                result["resolved_career_url"] = final_url
                html = resp.read().decode("utf-8", errors="ignore")

                # 檢測 RSS / Atom Feed
                rss_match = re.search(
                    r'<link[^>]+(?:type=[\"\']application/(?:rss|atom)\+xml[\"\']|type=[\"\']text/xml[\"\'])[^>]*href=[\"\']([^\"\']+)[\"\']',
                    html,
                    re.I
                )
                if rss_match:
                    result["has_rss"] = True
                    result["rss_url"] = urllib.parse.urljoin(final_url, rss_match.group(1))

                lower_html = html.lower()
                lower_url = final_url.lower()
                if "myworkdayjobs.com" in lower_url or "wday/cxs" in lower_html:
                    result["ats_type"] = "Workday"
                elif "eightfold.ai" in lower_html or "careers.qualcomm.com" in lower_url:
                    result["ats_type"] = "Eightfold"
                elif "greenhouse.io" in lower_html or "greenhouse.io" in lower_url:
                    result["ats_type"] = "Greenhouse"
                elif "lever.co" in lower_html or "lever.co" in lower_url:
                    result["ats_type"] = "Lever"
                elif "smartrecruiters.com" in lower_html:
                    result["ats_type"] = "SmartRecruiters"
                elif "api/trpc" in lower_html:
                    result["ats_type"] = "Next.js tRPC"
                elif "api_jobs" in lower_html:
                    result["ats_type"] = "Garmin API"
                else:
                    result["ats_type"] = "Custom / Web Portal"
        except Exception:
            pass
