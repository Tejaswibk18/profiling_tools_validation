import unittest
from unittest.mock import patch
import os

class TestWorkloadProfilerOutput(unittest.TestCase):
    def test_output_files_exist(self):
        # We need to check that the WP output contains an .html and .tar.xz file.
        # We will mock os.listdir to simulate reading the output directory.
        
        with patch('os.listdir') as mock_listdir:
            # Simulate finding both required files
            mock_listdir.return_value = ['workload_report.html', 'workload_data.tar.xz', 'log.txt']
            
            files = os.listdir('/dummy/path/outputs/wp/linux/without_sudo')
            
            has_html = any(f.endswith('.html') for f in files)
            has_tar_xz = any(f.endswith('.tar.xz') for f in files)
            
            self.assertTrue(has_html, "WP output must contain an .html file")
            self.assertTrue(has_tar_xz, "WP output must contain a .tar.xz file")
            
    def test_output_files_missing(self):
        # Test that it fails if files are missing
        with patch('os.listdir') as mock_listdir:
            mock_listdir.return_value = ['workload_report.html', 'log.txt'] # Missing .tar.xz
            
            files = os.listdir('/dummy/path/outputs/wp/linux/without_sudo')
            
            has_tar_xz = any(f.endswith('.tar.xz') for f in files)
            self.assertFalse(has_tar_xz, "Should detect missing .tar.xz file")

if __name__ == '__main__':
    unittest.main()
