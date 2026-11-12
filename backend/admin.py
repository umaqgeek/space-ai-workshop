"""Server-side browser admin sessions and shared workshop permissions."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager

from data.record_store import database_path

DEFAULTS = {'excerpt_only': False, 'allow_record_updates': True}
SESSION_SECONDS = 7 * 24 * 60 * 60


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=5)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS admin_sessions (token TEXT PRIMARY KEY, password_hash TEXT, expires REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (id INTEGER PRIMARY KEY CHECK (id = 1), body TEXT)')
        db.commit()
        yield db


def password_hash():
    return hashlib.sha256(os.environ.get('ADMIN_PASSWORD', '').encode()).hexdigest()


def login(password):
    expected = os.environ.get('ADMIN_PASSWORD', '')
    if not expected:
        raise RuntimeError('Admin access is not configured. Set ADMIN_PASSWORD on the server.')
    if not isinstance(password, str) or not hmac.compare_digest(password.encode(), expected.encode()):
        raise PermissionError('Incorrect admin password.')
    token = secrets.token_urlsafe(32)
    with connection() as db:
        db.execute('DELETE FROM admin_sessions WHERE expires <= ?', (time.time(),))
        db.execute('INSERT INTO admin_sessions VALUES (?, ?, ?)',
                   (hashlib.sha256(token.encode()).hexdigest(), password_hash(), time.time() + SESSION_SECONDS))
        db.commit()
    return token


def is_admin(authorization):
    if not os.environ.get('ADMIN_PASSWORD') or not authorization.startswith('Bearer '):
        return False
    token = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with connection() as db:
        return db.execute('SELECT 1 FROM admin_sessions WHERE token = ? AND password_hash = ? AND expires > ?',
                          (token, password_hash(), time.time())).fetchone() is not None


def logout(authorization):
    with connection() as db:
        db.execute('DELETE FROM admin_sessions WHERE token = ?',
                   (hashlib.sha256(authorization.removeprefix('Bearer ').encode()).hexdigest(),))
        db.commit()


def settings(changes=None):
    import json
    with connection() as db:
        if changes is not None:
            if changes.keys() != DEFAULTS.keys() or any(type(value) is not bool for value in changes.values()):
                raise ValueError('Provide excerpt_only and allow_record_updates as booleans.')
            db.execute('INSERT OR REPLACE INTO app_settings VALUES (1, ?)', (json.dumps(changes),))
            db.commit()
        row = db.execute('SELECT body FROM app_settings WHERE id = 1').fetchone()
    return json.loads(row[0]) if row else dict(DEFAULTS)
