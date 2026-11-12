"""Shared chat transcripts, stored alongside workshop records in SQLite."""
import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from data.record_store import database_path


def session_id(value=None):
    if value is None:
        return uuid.uuid4().hex
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Invalid conversation session ID.')
    return value


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS chat_exchanges (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            created_at TEXT NOT NULL, body TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS chat_session_exchanges ON chat_exchanges(session_id, id)')
        db.commit()
        yield db


def save_exchange(chat_id, result, settings):
    """Save the question and complete response together; never create empty histories."""
    timestamp = datetime.now(timezone.utc).isoformat()
    body = json.dumps(dict(result, settings=settings), ensure_ascii=False, allow_nan=False)
    with connection() as db:
        with db:
            db.execute('INSERT OR IGNORE INTO chat_sessions VALUES (?, ?, ?, ?)',
                       (chat_id, result['question'][:100], timestamp, timestamp))
            db.execute('INSERT INTO chat_exchanges (session_id, created_at, body) VALUES (?, ?, ?)',
                       (chat_id, timestamp, body))
            db.execute('UPDATE chat_sessions SET updated_at = ? WHERE id = ?', (timestamp, chat_id))


def list_sessions(offset=0, limit=30):
    with connection() as db:
        rows = db.execute('''SELECT s.*, COUNT(e.id) AS conversation_count
            FROM chat_sessions s JOIN chat_exchanges e ON e.session_id = s.id
            GROUP BY s.id ORDER BY s.updated_at DESC, s.id LIMIT ? OFFSET ?''',
                          (limit + 1, offset)).fetchall()
    return {'sessions': [dict(row) for row in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}


def get_session(chat_id):
    with connection() as db:
        row = db.execute('SELECT * FROM chat_sessions WHERE id = ?', (chat_id,)).fetchone()
        if row is None:
            return None
        exchanges = db.execute('SELECT created_at, body FROM chat_exchanges WHERE session_id = ? ORDER BY id',
                               (chat_id,)).fetchall()
    return dict(row, conversations=[dict(json.loads(item['body']), created_at=item['created_at'])
                                    for item in exchanges])
