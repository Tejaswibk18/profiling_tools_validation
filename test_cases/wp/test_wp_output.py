import unittest
from unittest.mock import patch
import os

class TestWorkloadProfilerOutput(unittest.TestCase):
    _use_real_dir = False
    real_dir_path = ""

    def test_output_files_exist(self):
        # If running on real data, read files from the real directory path.
        if self._use_real_dir:
            if not os.path.exists(self.real_dir_path):
                self.fail(f"Real WP output directory does not exist: {self.real_dir_path}")
            files = os.listdir(self.real_dir_path)
        else:
            # Standalone mockup behavior
            with patch('os.listdir') as mock_listdir:
                mock_listdir.return_value = ['workload_report.html', 'workload_data.tar.xz', 'log.txt']
                files = os.listdir('/dummy/path/outputs/wp/linux/without_sudo')
            
        has_html = any(f.endswith('.html') for f in files)
        has_tar_xz = any(f.endswith('.tar.xz') for f in files)
        
        self.assertTrue(has_html, "WP output must contain an .html file")
        self.assertTrue(has_tar_xz, "WP output must contain a .tar.xz file")
            
    def test_output_files_missing(self):
        # We only run mock tests during standalone execution
        if self._use_real_dir:
            return
            
        with patch('os.listdir') as mock_listdir:
            mock_listdir.return_value = ['workload_report.html', 'log.txt'] # Missing .tar.xz
            
            files = os.listdir('/dummy/path/outputs/wp/linux/without_sudo')
            
            has_tar_xz = any(f.endswith('.tar.xz') for f in files)
            self.assertFalse(has_tar_xz, "Should detect missing .tar.xz file")

if __name__ == '__main__':
    unittest.main()
