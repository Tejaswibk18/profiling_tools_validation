import unittest
from services.ssh_service import validate_keys

class TestCustomCases(unittest.TestCase):
    def test_bracketed_keys_format(self):
        # Sample data to test against
        data = {
            "Summary": {
                "Server": {
                    "Model": "ProLiant DL380"
                }
            }
        }
        
        # Checking the key in this exact way: [Summary.Server.Model]
        keys = ["[Summary.Server.Model]"]
        
        result = validate_keys(data, keys)
        
        # Verify that the original bracketed key is in the output and it passed
        self.assertIn("[Summary.Server.Model]", result)
        self.assertIn("FOUND", result)
        self.assertIn("ProLiant DL380", result)
        
    def test_multiple_bracketed_keys(self):
        data = {
            "Summary": {
                "Server": {
                    "Model": "ProLiant DL380",
                    "Health": "OK"
                }
            }
        }
        
        # Allowing multiple keys
        keys = ["[Summary.Server.Model]", "[Summary.Server.Health]"]
        
        result = validate_keys(data, keys)
        
        # Verify both keys are processed and found
        self.assertIn("[Summary.Server.Model] : FOUND", result)
        self.assertIn("[Summary.Server.Health] : FOUND", result)
        
    def test_key_not_found(self):
        data = {
            "Summary": {
                "Server": {
                    "Model": "ProLiant DL380"
                }
            }
        }
        
        keys = ["[Summary.Server.UnknownKey]"]
        
        result = validate_keys(data, keys)
        
        self.assertIn("[FAIL]", result)
        self.assertIn("KEY NOT FOUND", result)

if __name__ == '__main__':
    unittest.main()
