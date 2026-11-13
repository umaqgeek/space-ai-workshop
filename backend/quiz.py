"""Shared, server-timed quiz rounds. Answer keys never leave before completion."""
import hashlib
import json
import secrets
import sqlite3
import time
import unicodedata
from contextlib import closing, contextmanager
from pathlib import Path

from data.record_store import database_path

QUESTIONS = json.loads((Path(__file__).resolve().parents[1] / 'data/quiz_questions.json').read_text())
SECONDS = 10


class QuizConflict(ValueError):
    pass


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS quiz_round (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL, started REAL)')
        db.execute('INSERT OR IGNORE INTO quiz_round VALUES (1, 0, NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS quiz_players (
            token TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
            answers TEXT NOT NULL)''')
        db.commit()
        # Serialize registration, start, reset and answers across workers.
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def phase(row, now):
    if row['started'] is None:
        return 'lobby'
    return 'finished' if now >= row['started'] + len(QUESTIONS) * SECONDS else 'running'


def result(player):
    answers = json.loads(player['answers'])
    review = [dict(question=q['question'], options=q['options'], answer=q['answer'],
                   explanation=q['explanation'], selected=answers.get(str(i)),
                   correct=answers.get(str(i)) == q['answer']) for i, q in enumerate(QUESTIONS)]
    score = sum(item['correct'] for item in review)
    return {'name': player['name'], 'score': score, 'total': len(QUESTIONS),
            'percentage': round(score / len(QUESTIONS) * 100), 'review': review}


def snapshot(db, token='', administrative=False):
    row = db.execute('SELECT * FROM quiz_round WHERE id=1').fetchone()
    now = time.time()
    current_phase = phase(row, now)
    state = dict(enabled=bool(row['enabled']), phase=current_phase,
                 server_time=now, total=len(QUESTIONS), seconds=SECONDS,
                 registered=db.execute('SELECT COUNT(*) FROM quiz_players').fetchone()[0])
    if administrative:
        players = db.execute('SELECT * FROM quiz_players ORDER BY name_key').fetchall()
        state['players'] = [dict(name=p['name'], answered=len(json.loads(p['answers'])),
                                 result=result(p) if current_phase == 'finished' else None) for p in players]
        state['players'].sort(key=lambda p: -(p['result']['score'] if p['result'] else 0))
        return state
    if not row['enabled']:
        return state
    player = db.execute('SELECT * FROM quiz_players WHERE token=?', (digest(token),)).fetchone() if token else None
    if player:
        state['player'] = {'name': player['name']}
        if current_phase == 'finished':
            state['result'] = result(player)
        elif current_phase == 'running' and now < row['started']:
            state['starts_at'] = row['started']
        elif current_phase == 'running':
            index = int((now - row['started']) // SECONDS)
            q = QUESTIONS[index]
            state['question'] = dict(index=index, question=q['question'], options=q['options'],
                                     round=q['round'], deadline=row['started'] + (index + 1) * SECONDS,
                                     selected=json.loads(player['answers']).get(str(index)))
    return state


def state(token='', administrative=False):
    with connection() as db:
        return snapshot(db, token, administrative)


def register(name, token=''):
    if not isinstance(name, str):
        raise ValueError('Enter your name.')
    name = ' '.join(unicodedata.normalize('NFKC', name).split())
    if not 1 <= len(name) <= 60 or any(unicodedata.category(c).startswith('C') for c in name):
        raise ValueError('Enter a name between 1 and 60 characters, without control characters.')
    with connection() as db:
        row = db.execute('SELECT * FROM quiz_round WHERE id=1').fetchone()
        if not row['enabled'] or row['started'] is not None:
            raise QuizConflict('Registration is closed for this round.')
        if token and db.execute('SELECT 1 FROM quiz_players WHERE token=?', (digest(token),)).fetchone():
            raise QuizConflict('You have already joined. Wait for the admin to start or reset the round.')
        if db.execute('SELECT 1 FROM quiz_players WHERE name_key=?', (name.casefold(),)).fetchone():
            raise QuizConflict('That name is already registered for this round. Use your existing browser, or a distinct name if you are another person.')
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO quiz_players VALUES (?, ?, ?, ?)', (digest(token), name, name.casefold(), '{}'))
        return dict(snapshot(db, token), token=token)


def answer(token, index, selected):
    if type(index) is not int or not 0 <= index < len(QUESTIONS):
        raise ValueError('Invalid question.')
    if type(selected) is not int or not 0 <= selected < 4:
        raise ValueError('Choose one of the four answers.')
    with connection() as db:
        row = db.execute('SELECT * FROM quiz_round WHERE id=1').fetchone()
        player = db.execute('SELECT * FROM quiz_players WHERE token=?', (digest(token),)).fetchone()
        if not player:
            raise PermissionError('Register for the quiz first.')
        now = time.time()
        if not row['enabled'] or phase(row, now) != 'running' or index != int((now - row['started']) // SECONDS):
            raise QuizConflict('This question has closed. Your late answer was not saved.')
        answers = json.loads(player['answers'])
        answers[str(index)] = selected
        db.execute('UPDATE quiz_players SET answers=? WHERE token=?', (json.dumps(answers), player['token']))
        return snapshot(db, token)


def control(action, enabled=None):
    with connection() as db:
        if action == 'visibility':
            if type(enabled) is not bool:
                raise ValueError('Enabled must be true or false.')
            db.execute('UPDATE quiz_round SET enabled=? WHERE id=1', (enabled,))
        elif action == 'start':
            row = db.execute('SELECT * FROM quiz_round WHERE id=1').fetchone()
            if not row['enabled'] or row['started'] is not None:
                raise QuizConflict('Enable the quiz and reset any previous round before starting.')
            if not db.execute('SELECT 1 FROM quiz_players LIMIT 1').fetchone():
                raise QuizConflict('Wait for at least one player to register.')
            # Short shared countdown lets connected browsers receive the start.
            db.execute('UPDATE quiz_round SET started=? WHERE id=1', (time.time() + 3,))
        elif action == 'reset':
            db.execute('DELETE FROM quiz_players')
            db.execute('UPDATE quiz_round SET started=NULL WHERE id=1')
        else:
            raise ValueError('Unknown quiz action.')
        return snapshot(db, administrative=True)
