import unittest
import tempfile
import shutil
from pathlib import Path
from services.zip_service import archive_outputs, extract_archive
from unittest.mock import patch

class TestZipService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.outputs_dir = Path(self.test_dir) / "outputs" / "test_module"
        self.outputs_dir.mkdir(parents=True)
        (self.outputs_dir / "test_file.txt").write_text("dummy content")
        
        self.reports_dir = Path(self.test_dir) / "reports"
        self.reports_dir.mkdir(parents=True)

        self.patcher = patch("services.zip_service.Path")
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

    def test_archive_and_extract(self):
        # Test archive creation
        archive_outputs("test_module")
        zip_file = Path(self.test_dir) / "reports" / "test_module_results.zip"
        self.assertTrue(zip_file.exists())

        # Test extraction
        extract_dir = Path(self.test_dir) / "extracted"
        extract_archive(str(zip_file), str(extract_dir))
        
        extracted_file = extract_dir / "test_file.txt"
        self.assertTrue(extracted_file.exists())
        self.assertEqual(extracted_file.read_text(), "dummy content")

if __name__ == "__main__":
    unittest.main()
