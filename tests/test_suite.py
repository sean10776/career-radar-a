"""
Comprehensive Automated Test Suite for CareerRadar
可在 Sandbox 環境中完全自主運行 (Free-hand)
"""

import unittest
import os
import tempfile
from pathlib import Path
from career_radar.models import JobOpening
from career_radar.config import AppConfig, MatchingConfig, load_target_companies
from career_radar.storage import JobDatabase
from career_radar.extractor import ContentExtractor
from career_radar.resolver import JobSiteResolver
from career_radar.exporter import ObsidianExporter
from career_radar.utils.jsonc import parse_jsonc
from career_radar.utils.platform_net import detect_platform, get_processing_temp_dir


class TestCareerRadar(unittest.TestCase):

    def test_jsonc_parsing(self):
        """驗證 JSONC 解析器支援單行註解、多行註解與結尾逗號"""
        sample_jsonc = """
        {
            // 單行註解
            "name": "CareerRadar",
            /* 多行
               註解 */
            "url": "https://example.com/api",
            "items": [1, 2, 3,], // 包含 trailing comma
        }
        """
        data = parse_jsonc(sample_jsonc)
        self.assertEqual(data["name"], "CareerRadar")
        self.assertEqual(data["url"], "https://example.com/api")
        self.assertEqual(data["items"], [1, 2, 3])

    def test_config_loading(self):
        """驗證 AppConfig 動態載入與配置驅動能力"""
        cfg = AppConfig.load()
        self.assertIsNotNone(cfg.candidate)
        self.assertIsNotNone(cfg.matching)
        self.assertGreater(len(cfg.matching.core_keywords), 0)
        self.assertIn("Taiwan", cfg.matching.target_locations)

    def test_targets_catalog_jsonc(self):
        """驗證外部 targets.jsonc 目錄讀取與完整性"""
        targets = load_target_companies()
        self.assertGreaterEqual(len(targets), 40)
        categories = {t.get("category") for t in targets}
        self.assertIn("Taiwan Top IC", categories)
        self.assertIn("Dream Foreign", categories)

    def test_platform_and_temp_directory(self):
        """驗證跨平台與處理中暫存目錄隔離至 tmp/"""
        plat = detect_platform()
        self.assertIn(plat, ["windows", "wsl", "linux"])

        tmp_dir = get_processing_temp_dir("test_career_radar")
        self.assertTrue(tmp_dir.exists())
        self.assertTrue(str(tmp_dir).startswith(tempfile.gettempdir()))

    def test_config_driven_scoring(self):
        """驗證職缺比對評分完全由配置權重驅動"""
        matching_cfg = MatchingConfig(
            core_keywords=["Kernel", "BSP"],
            secondary_keywords=["I2C"],
            exclude_keywords=["HR", "Sales"],
            weights={"core_title": 50, "core_body": 25, "secondary_title": 20, "secondary_body": 10, "location_bonus": 15}
        )

        job = JobOpening(
            id="test:1",
            company_id="corp",
            company_name="Corp",
            title="Kernel & BSP Lead",
            url="https://example.com",
            location="Taiwan"
        )
        score = job.evaluate_fit(config=matching_cfg)
        # core_title (50) + location_bonus (15) = 65
        self.assertGreaterEqual(score, 65)

    def test_storage_and_processing_marker(self):
        """驗證暫存標記與資料庫儲存"""
        test_db_path = Path(tempfile.gettempdir()) / "test_career_radar_db.json"
        if test_db_path.exists():
            test_db_path.unlink()

        db = JobDatabase(data_path=str(test_db_path))
        db.write_processing_marker("TestCompany", "Step 1/1")
        self.assertTrue((db.processing_dir / "current_task.json").exists())

        job = JobOpening(
            id="comp:001",
            company_id="comp",
            company_name="Corp",
            title="Driver Engineer",
            url="https://example.com",
            location="Taiwan"
        )
        new_c, up_c = db.save_jobs([job])
        self.assertEqual(new_c, 1)

        db.clear_processing_marker()
        self.assertFalse((db.processing_dir / "current_task.json").exists())

    def test_exporter_markdown(self):
        """驗證 Obsidian 看板輸出"""
        test_md = Path(tempfile.gettempdir()) / "test_dash.md"
        db = JobDatabase(data_path=str(Path(tempfile.gettempdir()) / "test_dummy.json"))
        exporter = ObsidianExporter(output_path=str(test_md))
        exporter.export(db)
        self.assertTrue(test_md.exists())


if __name__ == "__main__":
    unittest.main()
