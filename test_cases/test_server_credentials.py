import unittest
from unittest.mock import patch
from services.ssh_service import load_server_details
import configparser

class TestServerCredentials(unittest.TestCase):
    @patch("configparser.ConfigParser.read")
    @patch("configparser.ConfigParser.has_section")
    @patch("configparser.ConfigParser.get")
    def test_load_server_details_success(self, mock_get, mock_has_section, mock_read):
        mock_has_section.return_value = True
        
        def mock_get_side_effect(section, key, fallback=None):
            if key == "ip": return "192.168.1.100"
            if key == "username": return "admin"
            if key == "password": return "secret"
            if key == "ssh_key": return None
            return fallback
        
        mock_get.side_effect = mock_get_side_effect
        
        details = load_server_details("linux")
        self.assertEqual(details["host"], "192.168.1.100")
        self.assertEqual(details["username"], "admin")
        self.assertEqual(details["password"], "secret")
        self.assertIsNone(details["key_path"])

    @patch("configparser.ConfigParser.read")
    @patch("configparser.ConfigParser.has_section")
    def test_load_server_details_missing_section(self, mock_has_section, mock_read):
        mock_has_section.return_value = False
        with self.assertRaises(ValueError):
            load_server_details("nonexistent_os")

if __name__ == "__main__":
    unittest.main()
