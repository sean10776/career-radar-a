"""
Unified Command Line Interface for CareerRadar
完全由 JSONC 配置檔驅動，支援 Windows, Linux 與 WSL 跨平台執行
"""

import argparse
import sys
import shutil
from pathlib import Path
from typing import List, Optional
from .config import AppConfig, load_target_companies
from .resolver import JobSiteResolver
from .extractor import ContentExtractor
from .llm_client import LocalLLMClient
from .storage import JobDatabase
from .exporter import ObsidianExporter
from .models import JobOpening
from .agentic_hunter import AgenticHunter


def handle_models(args, config: AppConfig):
    endpoint = args.endpoint or config.llm.endpoint
    client = LocalLLMClient(
        llm_config=config.llm,
        candidate_config=config.candidate,
        override_endpoint=args.endpoint
    )

    print("=" * 60)
    print(f"🔍 正在連線 LLM 服務查詢可用模型 ({client.endpoint})...")
    print("=" * 60)

    models = client.get_models()

    if not models:
        print("⚠️ 無法連線至 LLM 服務或尚未載入任何模型。")
        print("💡 請確認：")
        print("   1. LM Studio 或 Ollama 是否已啟動 Local Server。")
        print("   2. 若在 WSL 中執行，確認 Windows 上的 LM Studio 已勾選 'Serve on Local Network'。")
        print("   3. 推薦模型清單 (針對 8GB VRAM)：")
        for pref in config.llm.preferred_models:
            print(f"      • {pref}")
    else:
        rec_model = client.get_recommended_model()
        print(f"✅ 成功連線！就緒模型清單 ({len(models)} 個)：")
        for i, m in enumerate(models, 1):
            tag = " ⭐ (系統推薦)" if m == rec_model else ""
            print(f"   [{i}] {m}{tag}")
        print("\n💡 配置評估：")
        print(f"   - **推薦模型**：`{rec_model}`")
        print("   - 建議 Context Length 設定為 4096 ~ 8192。")
    print("=" * 60)


def handle_resolve(args, config: AppConfig):
    target = args.target
    print("=" * 60)
    print(f"🔍 正在反推目標公司/連結的官方 Job Site：{target}")
    print("=" * 60)

    resolver = JobSiteResolver(config=config.crawler)
    hint = target if target.startswith("http") else None
    comp_name = target if not target.startswith("http") else "CustomTarget"

    res = resolver.resolve(comp_name, hint_url=hint)
    print(f"• 目標名稱/輸入：{target}")
    print(f"• 反推官方 Job Site：{res['resolved_career_url'] or '未找到'}")
    print(f"• ATS 架構判斷：{res['ats_type']}")
    print(f"• RSS / Atom 介面：{'✅ 有 (' + str(res['rss_url']) + ')' if res['has_rss'] else '❌ 無公開 RSS'}")
    if res.get("candidates"):
        print("\n候選相關連結：")
        for c in res["candidates"][:3]:
            print(f"   - {c}")
    print("=" * 60)


def handle_run(args, config: AppConfig, targets_list: list):
    resolver = JobSiteResolver(config=config.crawler)
    extractor = ContentExtractor(crawler_config=config.crawler, matching_config=config.matching)
    llm = LocalLLMClient(
        llm_config=config.llm,
        candidate_config=config.candidate,
        override_endpoint=args.endpoint,
        override_model=args.model
    )
    db = JobDatabase(data_path=args.output_data, config=config.storage)
    exporter = ObsidianExporter(
        output_path=args.output_dashboard,
        storage_config=config.storage,
        matching_config=config.matching
    )

    print("=" * 60)
    print("🚀 啟動 CareerRadar 職缺雷達管線")
    print(f"• LLM 端點：{llm.endpoint}")
    if llm.model:
        print(f"• 指定模型：{llm.model}")
    print(f"• 候選人畫像：{config.candidate.name} ({', '.join(config.candidate.target_roles[:2])}...)")
    print(f"• 暫存處理目錄：{db.processing_dir}")
    print("=" * 60)

    # 決定處理的公司目標
    targets = []
    if args.company:
        matches = [c for c in targets_list if args.company.lower() in c.get("name", "").lower() or args.company.lower() == c.get("id", "").lower()]
        if matches:
            targets = matches
        else:
            targets = [{
                "id": args.company.lower().replace(" ", "_"),
                "name": args.company,
                "category": "User Custom",
                "known_career_url": None
            }]
    elif args.category:
        targets = [c for c in targets_list if args.category.lower() in c.get("category", "").lower()]
    elif args.limit:
        targets = targets_list[:args.limit]
    else:
        targets = targets_list

    hunter = AgenticHunter(config=config, llm_client=llm)

    all_found_jobs: List[JobOpening] = []
    print(f"📋 即將處理 {len(targets)} 家目標公司 (Agentic 模式)...\n")

    for idx, comp in enumerate(targets, 1):
        name = comp["name"]
        comp_id = comp.get("id", name.lower().replace(" ", "_"))
        db.write_processing_marker(name, f"Processing {idx}/{len(targets)}")
        print(f"[{idx}/{len(targets)}] 🏢 正在處理：{name}")

        known = comp.get("known_career_url")
        res = resolver.resolve(name, hint_url=known)
        job_site = res["resolved_career_url"] or known

        if not job_site:
            print("   ⚠️ 無法反推該公司 Job Site，跳過")
            continue

        rss_tag = f" [發現 RSS: {res['rss_url']}]" if res["has_rss"] else ""
        print(f"   -> 官方招募網址：{job_site}{rss_tag}")

        max_p = getattr(args, "pages", 3) or 3
        print(f"   -> 啟動 Agentic 探測 (意圖過濾 + 自動深度翻頁 {max_p} 頁)...")
        jobs = hunter.hunt_company(
            company_id=comp_id,
            company_name=name,
            job_site_url=job_site,
            max_pages=max_p
        )

        if jobs:
            print(f"   ✅ Agentic 探測成功！挖掘出 {len(jobs)} 筆精準職缺！")
            for j in jobs[:3]:
                print(f"      • [{j.match_score}分] {j.title} ({j.location})")
            all_found_jobs.extend(jobs)
        else:
            print("   ℹ️ 進入通用降級模式 (提取文本 + LLM 解析)...")
            extract_res = extractor.extract_text(job_site)
            text_content = extract_res.get("text", "")
            if text_content:
                jobs = llm.parse_job_text(company_name=name, site_url=job_site, raw_text=text_content)
                for j in jobs:
                    j.evaluate_fit(config=config.matching)
                if jobs:
                    print(f"   ✅ LLM 解析成功！挖掘出 {len(jobs)} 筆職缺！")
                    for j in jobs[:3]:
                        print(f"      • [{j.match_score}分] {j.title} ({j.location})")
                    all_found_jobs.extend(jobs)
                else:
                    print("   ⚠️ 未發現符合條件之職缺")
            else:
                print("   ⚠️ 網頁文本為空或抓取失敗，跳過")

    db.clear_processing_marker()

    new_c, up_c = db.save_jobs(all_found_jobs)
    print("\n" + "=" * 60)
    print(f"📊 資料庫持久化完成：新增 {new_c} 筆，更新 {up_c} 筆！ (儲存位置: {db.data_path})")

    exporter.export(db, all_found_jobs)
    print(f"📝 看板已同步更新至：{exporter.output_path}")
    print("=" * 60)


def handle_list_targets(args, targets_list: list):
    print("=" * 60)
    print(f"🏢 內建目標公司庫（共 {len(targets_list)} 家）：")
    print("=" * 60)
    categories = {}
    for c in targets_list:
        categories.setdefault(c.get("category", "其他"), []).append(c["name"])

    for cat, names in categories.items():
        print(f"\n【{cat}】({len(names)} 家)：")
        print("  " + "、".join(names))
    print("\n" + "=" * 60)


def handle_init_config(args):
    target = Path.cwd() / "config.jsonc"
    template = Path(__file__).parent.parent / "config.example.jsonc"
    if target.exists() and not args.force:
        print(f"⚠️ 當前目錄已存在 {target.name}，使用 --force 可覆蓋。")
        return

    if template.exists():
        shutil.copyfile(template, target)
        print(f"✅ 已成功建立配置檔範本：{target}")
    else:
        print("❌ 找不到範本檔案 config.example.jsonc")


def main():
    parser = argparse.ArgumentParser(
        description="CareerRadar: 整合反推 Job Site、通用爬取與 Local LLM 的職缺雷達",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="自訂 config.jsonc 或 config.json 路徑")
    parser.add_argument("--targets", help="自訂 targets.jsonc 或 targets.json 目錄路徑")

    subparsers = parser.add_subparsers(dest="command", help="子指令")

    # run
    run_parser = subparsers.add_parser("run", help="反推 Job Site 並透過 Local LLM 解析職缺")
    run_parser.add_argument("--company", "-c", help="指定單一公司名稱或招募連結")
    run_parser.add_argument("--category", help="指定公司類別")
    run_parser.add_argument("--limit", type=int, help="限制處理公司數量 (若未指定則預設處理全部公司)")
    run_parser.add_argument("--pages", type=int, default=3, help="Agentic 深度翻頁上限 (預設: 3 頁)")
    run_parser.add_argument("--endpoint", help="覆寫 LLM API 端點")
    run_parser.add_argument("--model", help="指定使用的 LLM 模型名稱")
    run_parser.add_argument("--output-data", help="自訂 JSON 資料庫輸出路徑")
    run_parser.add_argument("--output-dashboard", help="自訂 Markdown 看板輸出路徑")

    # models
    model_parser = subparsers.add_parser("models", help="查詢 Local LLM 當前就緒的模型清單與建議")
    model_parser.add_argument("--endpoint", help="覆寫 LLM API 端點")

    # resolve
    res_parser = subparsers.add_parser("resolve", help="測試從公司名稱或第三方連結反推官方 Job Site 與 RSS")
    res_parser.add_argument("target", help="公司名稱或連結")

    # list-targets
    subparsers.add_parser("list-targets", help="列出內建目標公司清單")

    # init-config
    init_parser = subparsers.add_parser("init-config", help="在當前目錄產生 config.jsonc 範本")
    init_parser.add_argument("--force", "-f", action="store_true", help="若已存在則強制覆蓋")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 載入設定檔與目標目錄
    config = AppConfig.load(args.config)
    targets = load_target_companies(args.targets)

    if args.command == "run":
        handle_run(args, config, targets)
    elif args.command == "models":
        handle_models(args, config)
    elif args.command == "resolve":
        handle_resolve(args, config)
    elif args.command == "list-targets":
        handle_list_targets(args, targets)
    elif args.command == "init-config":
        handle_init_config(args)


if __name__ == "__main__":
    main()
