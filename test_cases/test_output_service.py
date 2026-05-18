import unittest
import tempfile
import shutil
from pathlib import Path
from services.output_service import create_output_folders, save_output
from unittest.mock import patch

class TestOutputService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("services.output_service.Path")
    def test_create_output_folders(self, mock_path_class):
        def path_side_effect(arg):
            return Path(self.test_dir) / arg
        mock_path_class.side_effect = path_side_effect

        paths = create_output_folders("test_mod", "linux")
        
        self.assertIn("sudo", paths)
        self.assertIn("non_sudo", paths)
        self.assertTrue(paths["sudo"].exists())
        self.assertTrue(paths["non_sudo"].exists())
        self.assertTrue(str(paths["sudo"]).endswith("with_sudo"))
        self.assertTrue(str(paths["non_sudo"]).endswith("without_sudo"))

    def test_save_output(self):
        target_path = Path(self.test_dir)
        save_output(target_path, "test_file.txt", "Hello World")
        
        saved_file = target_path / "test_file.txt"
        self.assertTrue(saved_file.exists())
        self.assertEqual(saved_file.read_text(encoding="utf-8"), "Hello World")

if __name__ == "__main__":
    unittest.main()
