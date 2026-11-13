"""Quiz timing, lifecycle, authorization and answer-key isolation."""
import io
import json
import os
import sqlite3
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
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
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
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token=token)[0], 409)
        self.clock.return_value = 1003
        q = self.request('/api/quiz', token=token)[1]['question']
        self.assertEqual(q['index'], 0)
        self.assertEqual(q['deadline'], 1013)
        self.assertNotIn('answer', q)
        self.assertNotIn('explanation', q)
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token=token)[0], 200)
        self.clock.return_value = 1012.99
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':0}, token=token)[0], 409)
        self.clock.return_value = 1013
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':1}, token=token)[0], 409)
        self.assertEqual(self.request('/api/quiz', token=token)[1]['question']['index'], 1)
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
        r = self.request('/api/quiz', token=token)[1]['result']
        self.assertEqual(r['score'], 1)
        self.assertEqual(r['review'][0]['selected'], 1)
        self.assertIsNone(r['review'][1]['selected'])
        self.assertEqual(self.request('/api/quiz/answer', {'index':14,'selected':2}, token=token)[0], 409)

    def test_all_pdf_answers_score_and_admin_results(self):
        token = self.start()
        for i, q in enumerate(quiz.QUESTIONS):
            self.clock.return_value = 1003 + sum(item['seconds'] for item in quiz.QUESTIONS[:i])
            self.assertEqual(self.request('/api/quiz/answer', {'index':i,'selected':q['answer']}, token=token)[0], 200)
        self.assertNotIn('result', self.request('/api/quiz', token=token)[1])
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
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
        self.clock.return_value = 1003 + sum(q['seconds'] for q in quiz.QUESTIONS[:10])
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

    def test_variable_timers_at_exact_boundaries(self):
        token = self.start()
        starts = [1003] + [1003 + end for end in quiz.QUESTION_ENDS[:-1]]
        for i, (q, start) in enumerate(zip(quiz.QUESTIONS, starts)):
            for timestamp in (start, start + q['seconds'] - 0.001):
                self.clock.return_value = timestamp
                state = self.request('/api/quiz', token=token)[1]
                self.assertEqual(state['phase'], 'running')
                self.assertEqual(state['question']['index'], i)
                self.assertEqual(state['question']['seconds'], q['seconds'])
                self.assertEqual(state['question']['deadline'], start + q['seconds'])
        self.assertEqual(quiz.QUESTIONS[12]['seconds'], 20)
        self.assertEqual(quiz.TOTAL_SECONDS, 190)
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
        self.assertEqual(self.request('/api/quiz', token=token)[1]['phase'], 'finished')

    def test_first_answer_stays_locked_across_requests_and_concurrent_tabs(self):
        token = self.start()
        self.clock.return_value = 1003
        def choose(selected):
            try:
                quiz.answer(token, 0, selected)
                return selected
            except quiz.QuizConflict:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            choices = list(pool.map(choose, range(4)))
        winners = [choice for choice in choices if choice is not None]
        self.assertEqual(len(winners), 1)
        saved = self.request('/api/quiz', token=token)[1]['question']['selected']
        self.assertEqual(saved, winners[0])
        for selected in range(4):
            status, body = self.request('/api/quiz/answer', {'index':0,'selected':selected}, token=token)
            self.assertEqual(status, 409)
            self.assertIn('locked', body['error'])
        self.assertEqual(self.request('/api/quiz', token=token)[1]['question']['selected'], saved)
        self.clock.return_value = 1013
        self.assertEqual(self.request('/api/quiz/answer', {'index':1,'selected':2}, token=token)[0], 200)

    def test_response_times_are_server_measured_persisted_and_locked(self):
        token = self.start()
        self.clock.return_value = 1004.25
        status, accepted = self.request('/api/quiz/answer', {
            'index':0, 'selected':1, 'response_time_ms':0, 'answered_at':1003,
        }, token=token)
        self.assertEqual(status, 200)
        self.assertNotIn('response_time_ms', accepted['question'])
        self.assertNotIn('result', accepted)
        self.clock.return_value = 1010
        self.assertEqual(self.request('/api/quiz/answer', {'index':0,'selected':0}, token=token)[0], 409)
        self.assertEqual(self.request('/api/quiz', token=token)[1]['question']['selected'], 1)
        # Q2 starts at 1013, independently of when Q1 was answered.
        self.clock.return_value = 1015.75
        self.assertEqual(self.request('/api/quiz/answer', {'index':1,'selected':1}, token=token)[0], 200)
        # Q3 starts after the longer Q2 timer, at 1028. A wrong answer's
        # timing is recorded for review but excluded from the tie-break sum.
        self.clock.return_value = 1028.5
        self.assertEqual(self.request('/api/quiz/answer', {'index':2,'selected':0}, token=token)[0], 200)
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
        personal = self.request('/api/quiz', token=token)[1]['result']
        self.assertEqual(personal['score'], 2)
        self.assertEqual(personal['correct_time_ms'], 4000)
        self.assertEqual(personal['rank'], 1)
        self.assertFalse(personal['timing_estimated'])
        self.assertEqual([r['response_time_ms'] for r in personal['review'][:4]], [1250, 2750, 500, None])
        self.assertEqual(self.request('/api/admin/quiz', admin=self.admin)[1]['players'][0]['result'], personal)
        # Re-reading persisted results never changes their time or rank.
        self.clock.return_value += 50
        self.assertEqual(self.request('/api/quiz', token=token)[1]['result'], personal)
        self.control('reset')
        new_token = self.join()
        with quiz.connection() as db:
            player = db.execute('SELECT * FROM quiz_players WHERE token=?', (quiz.digest(new_token),)).fetchone()
            self.assertEqual(json.loads(player['answer_times']), {})

    def test_rank_by_score_then_correct_answer_time_and_share_exact_ties(self):
        self.control('visibility', enabled=True)
        tokens = {name:self.join(name) for name in ('A Slow', 'B Fast', 'C More Correct', 'D Wrong', 'E Equally Fast')}
        self.control('start')
        # Higher scores win regardless of time. B and E have identical
        # correct-answer totals; fast wrong answers must never improve a rank.
        submissions = [
            (1003.1, 'D Wrong', 0, 0),
            (1005, 'B Fast', 0, 1), (1005, 'E Equally Fast', 0, 1),
            (1007, 'A Slow', 0, 1), (1011, 'C More Correct', 0, 1),
            (1016, 'B Fast', 1, 1), (1016, 'E Equally Fast', 1, 1),
            (1020, 'A Slow', 1, 1), (1025, 'C More Correct', 1, 1),
            (1028.1, 'A Slow', 2, 0), (1037, 'C More Correct', 2, 2),
        ]
        for timestamp, name, index, selected in submissions:
            self.clock.return_value = timestamp
            self.assertEqual(self.request('/api/quiz/answer', {'index':index,'selected':selected}, token=tokens[name])[0], 200)
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
        players = self.request('/api/admin/quiz', admin=self.admin)[1]['players']
        self.assertEqual([p['name'] for p in players], ['C More Correct', 'B Fast', 'E Equally Fast', 'A Slow', 'D Wrong'])
        self.assertEqual([p['result']['rank'] for p in players], [1, 2, 2, 4, 5])
        self.assertEqual([p['result']['correct_time_ms'] for p in players], [29000, 5000, 5000, 11000, 0])
        for player in players:
            personal = self.request('/api/quiz', token=tokens[player['name']])[1]
            self.assertEqual(personal['result'], player['result'])
            self.assertNotIn('players', personal)

    def test_legacy_database_upgrade_preserves_answers_and_marks_missing_times(self):
        # Reproduce the schema from before timing capture was introduced.
        with sqlite3.connect(str(quiz.database_path())) as db:
            db.execute('CREATE TABLE quiz_round (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL, started REAL)')
            db.execute('INSERT INTO quiz_round VALUES (1, 1, 1003)')
            db.execute('CREATE TABLE quiz_players (token TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL, answers TEXT NOT NULL)')
            db.execute('INSERT INTO quiz_players VALUES (?, ?, ?, ?)',
                       (quiz.digest('legacy'), 'Legacy Player', 'legacy player', json.dumps({'0':1, '1':0})))
        db.close()
        self.clock.return_value = 1003 + quiz.TOTAL_SECONDS
        personal = self.request('/api/quiz', token='legacy')[1]['result']
        self.assertEqual(personal['score'], 1)
        self.assertEqual(personal['correct_time_ms'], 10000)
        self.assertTrue(personal['timing_estimated'])
        self.assertIsNone(personal['review'][0]['response_time_ms'])
        self.assertEqual(personal['rank'], 1)
        self.assertEqual(self.request('/api/admin/quiz', admin=self.admin)[1]['players'][0]['result'], personal)
        self.control('reset')
        self.join('New Player')

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
