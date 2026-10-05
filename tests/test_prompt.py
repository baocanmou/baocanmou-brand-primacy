import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PromptTests(unittest.TestCase):
    def test_prompt_is_up_to_date(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_prompt.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_prompt_has_no_dangling_reference_links(self):
        text = (ROOT / 'PROMPT.md').read_text(encoding='utf-8')
        self.assertNotIn('](references/', text)


if __name__ == '__main__':
    unittest.main()
