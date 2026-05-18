import unittest
from services.ssh_service import validate_keys

class TestValidateKeys(unittest.TestCase):
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

    def test_validate_keys_found(self):
        keys = ["[chassis.systems.bios.version]"]
        validation_output = validate_keys(self.dummy_data, keys)
        self.assertIn("[PASS]", validation_output)
        self.assertIn("FOUND -> 1.0", validation_output)

    def test_validate_keys_null(self):
        keys = ["[chassis.systems.bios.vendor]"]
        validation_output = validate_keys(self.dummy_data, keys)
        self.assertIn("[PASS]", validation_output)
        self.assertIn("NULL VALUE", validation_output)

    def test_validate_keys_missing(self):
        keys = ["[chassis.systems.bios.release_date]"]
        validation_output = validate_keys(self.dummy_data, keys)
        self.assertIn("[FAIL]", validation_output)
        self.assertIn("KEY NOT FOUND", validation_output)

if __name__ == "__main__":
    unittest.main()
