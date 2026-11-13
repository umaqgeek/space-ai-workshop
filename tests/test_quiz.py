"""Quiz timing, lifecycle, authorization and answer-key isolation."""
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from backend import quiz
from backend.webapp import application


class QuizTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {'SPACELAB_DATA_DIR': directory.name, 'ADMIN_PASSWORD': 'quiz-admin'})
        env.start()
        self.addCleanup(env.stop)
        clock = patch('backend.quiz.time.time', return_value=1000)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.admin = self.request('/api/admin/login', {'password': 'quiz-admin'})[1]['token']

    def request(self, path, data=None, token='', admin=''):
        body = json.dumps(data).encode() if data is not None else b''
        env = {'REQUEST_METHOD': 'POST' if data is not None else 'GET', 'PATH_INFO':path,
               'CONTENT_LENGTH':str(len(body)), 'CONTENT_TYPE':'application/json',
               'HTTP_AUTHORIZATION':'Bearer ' + admin, 'HTTP_X_QUIZ_TOKEN': token,
               'wsgi.input':io.BytesIO(body)}
        status = []
        result = b''.join(application(env, lambda s, h: status.append(int(s.split()[0]))))
        return status[0], json.loads(result)

    def control(self, action, **kwargs):
        status, data = self.request('/api/admin/quiz', dict(action=action, **kwargs), admin=self.admin)
        self.assertEqual(status, 200, data)
        return data

    def join(self, name='Player One'):
        status, data = self.request('/api/quiz/register', {'name':name})
        self.assertEqual(status, 200, data)
        return data['token']

    def start(self):
        self.control('visibility', enabled=True)
        token = self.join()
        self.control('start')
        return token

    def test_disabled_defaults_and_admin_authorization(self):
        self.assertFalse(self.request('/api/quiz')[1]['enabled'])
        self.assertEqual(self.request('/api/quiz/register', {'name':'A'})[0], 409)
        for data in ({'action':'start'}, {'action':'reset'}, {'action':'visibility','enabled':True}):
            self.assertEqual(self.request('/api/admin/quiz', data)[0], 403)
        self.assertEqual(self.request('/api/admin/quiz')[0], 403)
        self.assertEqual(self.request('/data/quiz_questions.json')[0], 404)
        from backend.webapp import dispatch
        status, headers, body = dispatch('GET', '/quiz.js', {}, io.BytesIO())
        self.assertEqual(status, 200)
        self.assertIn(b'/api/quiz', body)
        self.assertEqual(self.request('/api/admin/quiz', {'action':'visibility', 'enabled':'true'}, admin=self.admin)[0], 400)

    def test_registration_start_and_replay_locks(self):
        self.control('visibility', enabled=True)
        self.assertEqual(self.request('/api/admin/quiz', {'action':'start'}, admin=self.admin)[0], 409)
        token = self.join('  Ada   Lovelace ')
        self.assertEqual(self.request('/api/quiz', token=token)[1]['player']['name'], 'Ada Lovelace')
        self.assertEqual(self.request('/api/quiz/register', {'name':'ADA LOVELACE'})[0], 409)
        self.assertEqual(self.request('/api/quiz/register', {'name':'Other'}, token=token)[0], 409)
        self.control('start')
        self.assertEqual(self.request('/api/quiz/register', {'name':'Late Player'})[0], 409)
        self.assertEqual(self.request('/api/admin/quiz', {'action':'start'}, admin=self.admin)[0], 409)
        self.clock.return_value = 1153
        self.assertEqual(self.request('/api/quiz/register', {'name':'Other'}, token=token)[0], 409)
        self.assertEqual(self.request('/api/quiz', token=token)[1]['result']['score'], 0)
        self.control('reset')
        self.assertNotIn('player', self.request('/api/quiz', token=token)[1])
        self.assertNotEqual(self.join('Ada Lovelace'), token)

    def test_server_clock_auto_progresses_and_missing_answers_score_zero(self):
        token = self.start()
        countdown = self.request('/api/quiz', token=token)[1]
        self.assertEqual(countdown['starts_at'], 1003)
        self.assertNotIn('question', countdown)
        self.clock.return_value = 1003
        q = self.request('/api/quiz', token=token)[1]['question']
        self.assertEqual(q['index'], 0)
        self.assertEqual(q['deadline'], 1013)
        self.assertNotIn('answer', q)
        self.assertNotIn('explanation', q)
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token=token)[0], 200)
        self.clock.return_value = 1012.99
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':0}, token=token)[0], 200)
        self.clock.return_value = 1013
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token=token)[0], 409)
        self.assertEqual(self.request('/api/quiz', token=token)[1]['question']['index'], 1)
        self.clock.return_value = 1153
        r = self.request('/api/quiz', token=token)[1]['result']
        self.assertEqual(r['score'], 0)
        self.assertEqual(r['review'][0]['selected'], 0)
        self.assertIsNone(r['review'][1]['selected'])
        self.assertEqual(self.request('/api/quiz/answer', {'index':14,'selected':2}, token=token)[0], 409)

    def test_all_pdf_answers_score_and_admin_results(self):
        token = self.start()
        for i, q in enumerate(quiz.QUESTIONS):
            self.clock.return_value = 1003 + i * 10
            self.assertEqual(self.request('/api/quiz/answer', {'index':i,'selected':q['answer']}, token=token)[0], 200)
        self.assertNotIn('result', self.request('/api/quiz', token=token)[1])
        self.clock.return_value = 1153
        result = self.request('/api/quiz', token=token)[1]['result']
        self.assertEqual((result['score'], result['total'], result['percentage']), (15,15,100))
        results = self.request('/api/admin/quiz', admin=self.admin)[1]
        self.assertEqual(results['players'][0]['result'], result)
        self.assertNotIn('token', json.dumps(results))
        self.assertNotIn('result', self.request('/api/quiz', token='forged')[1])
        self.control('reset')
        self.assertEqual(self.request('/api/admin/quiz', admin=self.admin)[1]['players'], [])

    def test_visibility_persists_and_does_not_pause_round(self):
        token = self.start()
        self.control('visibility', enabled=False)
        self.clock.return_value = 1103
        self.assertNotIn('question', self.request('/api/quiz', token=token)[1])
        self.assertEqual(self.request('/api/quiz/answer', {'index':10,'selected':1}, token=token)[0], 409)
        self.control('visibility', enabled=True)
        self.assertEqual(self.request('/api/quiz', token=token)[1]['question']['index'], 10)

    def test_validation_and_forged_answers(self):
        self.control('visibility', enabled=True)
        for name in ('', ' ' * 5, 'a' * 61, 123, 'A\x00B'):
            self.assertEqual(self.request('/api/quiz/register', {'name':name})[0], 400)
        token = self.join()
        self.control('start')
        self.clock.return_value = 1003
        for selected in (True, None, -1, 4, 'B'):
            self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':selected}, token=token)[0], 400)
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token='fake')[0], 403)
        self.assertEqual(self.request('/api/quiz/answer', {'index':1,'selected':1}, token=token)[0], 409)

    def test_concurrent_duplicate_registration_is_atomic(self):
        self.control('visibility', enabled=True)
        def enroll(_):
            try:
                quiz.register('Same Name')
                return 'registered'
            except quiz.QuizConflict:
                return 'duplicate'
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(enroll, range(4)))
        self.assertEqual(results.count('registered'), 1)
        self.assertEqual(quiz.state()['registered'], 1)


if __name__ == '__main__':
    unittest.main()
