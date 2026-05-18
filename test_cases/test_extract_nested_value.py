import unittest
from services.ssh_service import extract_nested_value

class TestExtractNestedValue(unittest.TestCase):
    def setUp(self):
        self.dummy_data = {
            "chassis": {
                "systems": {
                    "bios": {
                        "version": "1.0",
                        "vendor": None
                    }
                }
            },
            "users": [
                {"address": {"city": "Phoenix"}},
                {"address": {"city": "Houston"}}
            ]
        }

    def test_extract_nested_value_single(self):
        keys = ["chassis", "systems", "bios", "version"]
        result = extract_nested_value(self.dummy_data, keys)
        self.assertEqual(result, ["1.0"])

    def test_extract_nested_value_list(self):
        keys = ["users", "address", "city"]
        result = extract_nested_value(self.dummy_data, keys)
        self.assertEqual(result, ["Phoenix", "Houston"])

if __name__ == "__main__":
    unittest.main()
