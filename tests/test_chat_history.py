import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from backend.webapp import application
from data import chat_store


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {'SPACELAB_DATA_DIR': directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def request(self, path, data=None):
        body = json.dumps(data).encode() if data is not None else b''
        path, _, query = path.partition('?')
        environ = {'REQUEST_METHOD': 'POST' if data is not None else 'GET',
                   'PATH_INFO': path, 'QUERY_STRING': query, 'CONTENT_LENGTH': str(len(body)),
                   'CONTENT_TYPE': 'application/json', 'wsgi.input': io.BytesIO(body)}
        statuses = []
        result = b''.join(application(environ, lambda status, headers: statuses.append(int(status.split()[0]))))
        return statuses[0], json.loads(result)

    def ask(self, **extra):
        status, result = self.request('/api/ask', {'question': 'flood in Klang', **extra})
        self.assertEqual(status, 200, result)
        return result

    def test_multiple_exchanges_share_one_persistent_session(self):
        first = self.ask()
        second = self.ask(session_id=first['session_id'], question='vegetation in Kuching')
        status, listing = self.request('/api/history')
        self.assertEqual(status, 200)
        self.assertEqual(len(listing['sessions']), 1)
        self.assertEqual(listing['sessions'][0]['conversation_count'], 2)
        # A separate request with no identity can read the complete transcript.
        status, saved = self.request('/api/history/' + first['session_id'])
        self.assertEqual(status, 200)
        self.assertEqual([item['question'] for item in saved['conversations']],
                         [first['question'], second['question']])
        for original, stored in zip((first, second), saved['conversations']):
            for key in original:
                self.assertEqual(original[key], stored[key])
            self.assertEqual(stored['settings']['mode'], 'offline')
        self.assertEqual(chat_store.get_session(first['session_id']), saved)

    def test_refresh_and_new_chat_start_separate_histories_without_empty_sessions(self):
        self.assertEqual(self.request('/api/history')[1]['sessions'], [])
        first, refreshed, new_chat = self.ask(), self.ask(), self.ask()
        self.assertEqual(len({item['session_id'] for item in (first, refreshed, new_chat)}), 3)
        self.assertEqual(len(self.request('/api/history')[1]['sessions']), 3)

    def test_invalid_requests_do_not_create_histories_or_call_model(self):
        with patch('backend.webapp.ask') as model:
            for changes in ({'question': 'x'}, {'session_id': '../../private'},
                            {'session_id': []}, {'mode': 'bad'}):
                self.assertEqual(self.request('/api/ask', {'question': 'flood', **changes})[0], 400)
            model.assert_not_called()
        self.assertEqual(self.request('/api/history')[1]['sessions'], [])
        self.assertEqual(self.request('/api/history/' + 'a' * 32)[0], 404)
        for suffix in ('/bad', '?offset=-1', '?offset=abc'):
            self.assertEqual(self.request('/api/history' + suffix)[0], 400)

    def test_failed_generation_does_not_save_partial_exchange(self):
        with patch('backend.webapp.ask', side_effect=OSError('unavailable')):
            self.assertEqual(self.request('/api/ask', {'question': 'flood'})[0], 500)
        self.assertEqual(self.request('/api/history')[1]['sessions'], [])

    def test_storage_failure_is_explicit(self):
        with patch('data.chat_store.save_exchange', side_effect=OSError('disk full')):
            status, result = self.request('/api/ask', {'question': 'flood'})
        self.assertEqual(status, 503)
        self.assertIn('Could not save', result['error'])
        self.assertEqual(self.request('/api/history')[1]['sessions'], [])

    def test_web_answer_and_source_snapshots_are_preserved(self):
        response = {'answer': 'External context [WEB-001]', 'sources': [], 'mode': 'qwen',
                    'web_sources': [{'id': 'WEB-001', 'content': 'Original excerpt', 'url': 'https://example.com'}],
                    'notice': None, 'status': 'matched'}
        with patch('backend.webapp.ask', return_value=response):
            result = self.ask(mode='qwen', web_search=True)
        saved = chat_store.get_session(result['session_id'])['conversations'][0]
        self.assertEqual(saved['web_sources'], response['web_sources'])
        self.assertTrue(saved['settings']['web_search'])

    def test_history_pagination(self):
        for number in range(32):
            chat_store.save_exchange(chat_store.session_id(), {'question': f'Question {number}', 'answer': 'answer'}, {})
        first = self.request('/api/history')[1]
        second = self.request('/api/history?offset=30')[1]
        self.assertEqual(len(first['sessions']), 30)
        self.assertEqual(first['next_offset'], 30)
        self.assertEqual(len(second['sessions']), 2)
        self.assertIsNone(second['next_offset'])
        self.assertFalse({row['id'] for row in first['sessions']} & {row['id'] for row in second['sessions']})

    def test_concurrent_saves_do_not_lose_exchanges(self):
        chat_id = chat_store.session_id()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda number: chat_store.save_exchange(chat_id, {'question': f'Question {number}'}, {}), range(12)))
        saved = chat_store.get_session(chat_id)['conversations']
        self.assertEqual(len(saved), 12)
        self.assertEqual(len({item['question'] for item in saved}), 12)

    def test_follow_up_uses_only_its_session_and_new_chat_resets_memory(self):
        first = self.ask()
        other = self.ask(question='vegetation in Kuching')
        follow_up = self.ask(question='What are its limitations?', session_id=first['session_id'])
        self.assertEqual(follow_up['context_turns'], 1)
        self.assertEqual([source['id'] for source in follow_up['sources']], ['FLOOD-001'])
        self.assertNotEqual(other['session_id'], first['session_id'])
        fresh = self.ask(question='What are its limitations?')
        self.assertEqual(fresh['context_turns'], 0)
        # An old shared session can be resumed with the same ID.
        resumed = self.ask(question='What about Kuching?', session_id=first['session_id'])
        self.assertEqual(resumed['context_turns'], 2)
        self.assertTrue(all(source['location'] == 'Kuching' and source['theme'] == 'flood'
                            for source in resumed['sources']))

    def test_recent_memory_is_bounded_and_ordered(self):
        chat_id = chat_store.session_id()
        for number in range(10):
            chat_store.save_exchange(chat_id, {'question': f'Question {number}', 'answer': 'Answer'}, {})
        recent = chat_store.recent_conversations(chat_id)
        self.assertEqual([turn['question'] for turn in recent], [f'Question {number}' for number in range(4, 10)])
        self.assertEqual(chat_store.recent_conversations(chat_store.session_id()), [])


if __name__ == '__main__':
    unittest.main()
