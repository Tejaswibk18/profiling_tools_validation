import unittest
import tempfile
import shutil
from pathlib import Path
from services.report_service import generate_html_report
from unittest.mock import patch

class TestReportService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Setup dummy outputs directory
        self.outputs_dir = Path(self.test_dir) / "outputs" / "test_mod" / "linux" / "with_sudo"
        self.outputs_dir.mkdir(parents=True)
        results_file = self.outputs_dir / "validation_results.txt"
        results_file.write_text("[PASS] key1 : FOUND\n[FAIL] key2 : NOT FOUND\n", encoding="utf-8")
        
        self.reports_dir = Path(self.test_dir) / "reports"

        self.patcher = patch("services.report_service.Path")
        self.mock_path = self.patcher.start()
        
        def path_side_effect(arg):
            if str(arg).startswith("outputs"):
                return Path(self.test_dir) / arg
            elif str(arg).startswith("reports"):
                return Path(self.test_dir) / arg
            return Path(arg)
            
        self.mock_path.side_effect = path_side_effect

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir)

    def test_generate_html_report(self):
        generate_html_report("test_mod")
        
        report_file = Path(self.test_dir) / "reports" / "html" / "test_mod_report.html"
        self.assertTrue(report_file.exists())
        
        content = report_file.read_text(encoding="utf-8")
        
        # Print content to see it in logs if it fails
        print("DEBUG CONTENT START")
        print(content)
        print("DEBUG CONTENT END")
        
        self.assertIn("Execution Report for Module: TEST_MOD", content)
        self.assertIn("Successful checks", content)
        self.assertIn("Issues detected", content)
        self.assertIn("key2 : NOT FOUND", content)

if __name__ == "__main__":
    unittest.main()
