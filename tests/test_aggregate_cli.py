"""Run the documented CLI with sibling collector fixtures, never live sources."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'community_aggregate.py'


class AggregateCliTests(unittest.TestCase):
    def run_cli(self, layout='checkout', collectors=None, sources=('hn',), extra=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / layout
            root.mkdir(parents=True)
            shutil.copyfile(SOURCE, root / SOURCE.name)
            for name, content in (collectors or {}).items():
                (root / name).write_text(content)
            result = subprocess.run(
                [sys.executable, str(root / SOURCE.name), 'hot', '--sources', *sources,
                 '--format', 'json', *extra], cwd=directory, capture_output=True, text=True,
                timeout=10)
            return result, json.loads(result.stdout)

    def test_sibling_dispatch_in_checkout_and_workspace_scripts_layout(self):
        for layout in ['checkout', 'workspace/scripts']:
            with self.subTest(layout=layout):
                result, data = self.run_cli(layout, {'hn_fetch.py':
                    'import json, sys\nassert sys.argv[1:3] == ["list", "top"]\n'
                    'print(json.dumps({"items": [{"title": "fixture", "url": "https://example.test/story"}]}))'})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(data['count'], 1)
                self.assertEqual(data['items'][0]['title'], 'fixture')
                self.assertEqual(data['errors'], [])

    def test_all_missing_collectors_fail_with_json_errors(self):
        result, data = self.run_cli(sources=('hn', 'dc'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data['count'], 0)
        self.assertEqual({e['source'] for e in data['errors']}, {'hn', 'dc'})

    def test_successful_empty_result_is_not_failure(self):
        result, data = self.run_cli(collectors={'hn_fetch.py': 'print(\'{"items": []}\')'})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['errors'], [])

    def test_partial_failure_keeps_successful_empty_source(self):
        result, data = self.run_cli(collectors={'hn_fetch.py': 'print(\'{"items": []}\')'}, sources=('hn', 'dc'))
        self.assertEqual(result.returncode, 0)
        self.assertEqual([e['source'] for e in data['errors']], ['dc'])

    def test_failed_newsfeeds_is_not_a_successful_article(self):
        result, data = self.run_cli(collectors={'news_feeds.py': 'raise SystemExit(3)'}, sources=('newsfeeds',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data['items'], [])
        self.assertEqual(data['errors'][0]['source'], 'newsfeeds')

    def test_filtering_all_items_does_not_turn_success_into_failure(self):
        result, data = self.run_cli(collectors={'hn_fetch.py': 'print(\'{"items": [{"title": "fixture"}]}\')'}, extra=('--bucket', 'news'))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['errors'], [])


if __name__ == '__main__':
    unittest.main()
