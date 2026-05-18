import unittest
from unittest.mock import patch, MagicMock
from services.ssh_service import get_profile_url

class TestConfigUrls(unittest.TestCase):
    @patch("services.ssh_service.load_config")
    def test_get_profile_url_found(self, mock_load_config):
        mock_config = MagicMock()
        mock_config.get.return_value = "https://example.com/api"
        mock_load_config.return_value = mock_config

        url = get_profile_url("pp", "linux")
        self.assertEqual(url, "https://example.com/api")
        mock_config.get.assert_called_once_with("platform_profiler", "linux", fallback="https://dummyjson.com/users")

    @patch("services.ssh_service.load_config")
    def test_get_profile_url_fallback(self, mock_load_config):
        mock_config = MagicMock()
        # If not found, it returns the fallback
        def side_effect(section, key, fallback=None):
            return fallback
        mock_config.get.side_effect = side_effect
        mock_load_config.return_value = mock_config

        url = get_profile_url("pp", "unknown_os")
        self.assertEqual(url, "https://dummyjson.com/users")

if __name__ == "__main__":
    unittest.main()
