import unittest
import argparse
from main import get_parser, get_selected_modules

class TestMainArgs(unittest.TestCase):
    def setUp(self):
        self.parser = get_parser()

    def test_pp_argument(self):
        args = self.parser.parse_args(["-pp"])
        modules = get_selected_modules(args)
        self.assertEqual(modules, [("pp", "Platform Profiler")])

    def test_all_argument(self):
        args = self.parser.parse_args(["-all"])
        modules = get_selected_modules(args)
        
        # Check that it extracted other modules
        keys = [mod_key for mod_key, _ in modules]
        self.assertIn("pp", keys)
        self.assertIn("wp", keys)
        
        # Should not contain '-all' itself
        self.assertNotIn("all", keys)

if __name__ == "__main__":
    unittest.main()
