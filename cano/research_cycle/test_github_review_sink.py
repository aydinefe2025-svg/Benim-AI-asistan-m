"""No-network test for durable GitHub issue sink, duplicate protection and readback."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import github_review_sink as sink


DATA = {
    'claims_verified': False, 'content_downloaded': False, 'topic': 'robotics',
    'items': [
        {'doi': '10.1234/a', 'title': 'Paper A', 'url': 'https://doi.org/10.1234/a'},
        {'doi': '10.1234/b', 'title': 'Paper B', 'url': 'https://doi.org/10.1234/b'},
    ]
}


class MemoryGitHub:
    def __init__(self):
        self.comments = []
        self.calls = []
    def __call__(self, url, token, method='GET', data=None):
        self.calls.append((url, method))
        if method == 'POST':
            self.comments.append({'body': data['body']})
            return {'id': len(self.comments), 'html_url': 'https://github.com/example/repo/issues/1#issuecomment-1'}
        if len(self.comments) == 0:
            return []
        if '?per_page=100&page=1' in url:
            return self.comments
        return []


class SinkTests(unittest.TestCase):
    def test_config_rejects_untrusted_values(self):
        for repo in ('http://127.0.0.1/a', '../a', 'a/../b', '', 'a\\b'):
            with self.assertRaises(sink.PublishError):
                sink.validate_issues_config(repo, 2, 'token_xxxxx')
        with self.assertRaises(sink.PublishError):
            sink.validate_issues_config('a/b', 0, 'token_xxxxx')
        with self.assertRaises(sink.PublishError):
            sink.validate_issues_config('a/b', 12, '')

    def test_first_persists_and_second_avoids_duplicates(self):
        s = MemoryGitHub()
        a = sink.publish(DATA, 'example/repo', 1, 'token_xxxxx', request=s)
        b = sink.publish(DATA, 'example/repo', 1, 'token_xxxxx', request=s)
        self.assertEqual((a['posted'], b['posted'], b['skipped']), (2, 0, 2))
        self.assertEqual(len(s.comments), 1)
        self.assertEqual(len([x for x in s.calls if x[1] == 'POST']), 1)
        self.assertIn('pending_review', s.comments[0]['body'])

    def test_partial_duplicate_only_posts_new(self):
        s = MemoryGitHub()
        sink.publish({'items':[DATA['items'][0]], 'topic':'robotics'}, 'a/b', 1, 'token_xxxxx', request=s)
        r = sink.publish(DATA, 'a/b', 1, 'token_xxxxx', request=s)
        self.assertEqual(r['posted'], 1)
        self.assertEqual(len(s.comments), 2)

    def test_fail_closed_if_cannot_read_all_history(self):
        def full(*args, **kwargs):
            return [{'body':'record'}] * 100
        with self.assertRaisesRegex(sink.PublishError, 'history too large'):
            sink.read_seen_markers('https://api.github.com/repos/a/b/issues/1/comments', 'token_xxxxx', request=full)

    def test_post_without_readback_fails(self):
        class NoReadback:
            def __init__(self):
                self.times = 0
            def __call__(self, url, token, method='GET', data=None):
                if method == 'POST':
                    return {'id': 4, 'html_url': 'https://github.com/a/b/issues/1#issuecomment-4'}
                return []
        with self.assertRaisesRegex(sink.PublishError, 'not visible'):
            sink.publish(DATA, 'a/b', 1, 'token_xxxxx', request=NoReadback())

    def test_malformed_paper_rejected_without_post(self):
        s = MemoryGitHub()
        bad = copy.deepcopy(DATA)
        bad['items'][0]['doi'] = 'javascript:alert(1)'
        with self.assertRaises(sink.PublishError):
            sink.publish(bad, 'a/b', 1, 'token_xxxxx', request=s)
        self.assertFalse(any(method == 'POST' for _, method in s.calls))

    def test_pending_input_validation(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / 'feed.json'
            file.write_text(json.dumps(DATA))
            self.assertEqual(len(sink.read_json(file)['items']), 2)
            file.write_text(json.dumps({**DATA, 'claims_verified': True}))
            with self.assertRaises(sink.PublishError):
                sink.read_json(file)


if __name__ == '__main__':
    unittest.main()
