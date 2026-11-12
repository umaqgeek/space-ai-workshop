import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.webapp import application


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {'SPACELAB_DATA_DIR': self.directory.name,
                                                    'ADMIN_PASSWORD': 'test-admin-秘密'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def request(self, path, data=None, token=''):
        body = json.dumps(data).encode() if data is not None else b''
        environ = {'REQUEST_METHOD': 'POST' if data is not None else 'GET',
                   'PATH_INFO': path, 'CONTENT_LENGTH': str(len(body)),
                   'CONTENT_TYPE': 'application/json',
                   'HTTP_AUTHORIZATION': f'Bearer {token}', 'wsgi.input': io.BytesIO(body)}
        statuses = []
        result = b''.join(application(environ, lambda status, headers: statuses.append(int(status.split()[0]))))
        return statuses[0], json.loads(result)

    def login(self):
        status, data = self.request('/api/admin/login', {'password': 'test-admin-秘密'})
        self.assertEqual(status, 200)
        self.assertNotIn('test-admin', json.dumps(data))
        return data['token']

    def test_login_logout_rotation_and_forgery(self):
        self.assertEqual(self.request('/api/admin/login', {'password': 'wrong'})[0], 403)
        token = self.login()
        self.assertEqual(self.request('/api/admin/session', token=token)[1], {'admin': True})
        self.assertEqual(self.request('/api/admin/session', token='true')[1], {'admin': False})
        with patch.dict(os.environ, {'ADMIN_PASSWORD': 'rotated'}):
            self.assertEqual(self.request('/api/admin/session', token=token)[1], {'admin': False})
        self.assertEqual(self.request('/api/admin/logout', {}, token)[0], 200)
        self.assertEqual(self.request('/api/admin/session', token=token)[1], {'admin': False})

    def test_unconfigured_admin_is_disabled(self):
        with patch.dict(os.environ, {'ADMIN_PASSWORD': ''}):
            self.assertEqual(self.request('/api/admin/login', {'password': ''})[0], 503)

    def test_settings_authorization_validation_and_persistence(self):
        settings = {'excerpt_only': True, 'allow_record_updates': False}
        self.assertEqual(self.request('/api/admin/settings', settings, 'forged')[0], 403)
        token = self.login()
        self.assertEqual(self.request('/api/admin/settings', {'excerpt_only': 'yes'}, token)[0], 400)
        self.assertEqual(self.request('/api/admin/settings', settings, token), (200, settings))
        self.assertEqual(self.request('/api/settings'), (200, settings))
        # Logging out must not reset the workshop's shared settings.
        self.request('/api/admin/logout', {}, token)
        self.assertEqual(self.request('/api/settings'), (200, settings))

    def test_restrictions_are_enforced_at_api(self):
        token = self.login()
        self.request('/api/admin/settings', {'excerpt_only': True, 'allow_record_updates': False}, token)
        with patch('backend.webapp.ask', return_value={'answer': 'excerpts'}) as ask:
            for payload in ({'mode': 'qwen'}, {'mode': 'offline', 'web_search': True}):
                self.assertEqual(self.request('/api/ask', dict(question='flood in Klang', **payload))[0], 403)
            ask.assert_not_called()
            self.assertEqual(self.request('/api/ask', {'question': 'flood in Klang', 'mode': 'offline'})[0], 200)
        with patch('backend.webapp.update_record', return_value={'id': 'FLOOD-001'}) as update:
            self.assertEqual(self.request('/api/records/FLOOD-001', {})[0], 403)
            update.assert_not_called()
            self.assertEqual(self.request('/api/records/FLOOD-001', {}, token)[0], 200)
        with patch('backend.webapp.import_csv') as importing:
            self.assertEqual(self.request('/api/records/import', {})[0], 403)
            importing.assert_not_called()

    def test_session_expiry(self):
        token = self.login()
        with patch('backend.admin.time.time', return_value=10**12):
            self.assertEqual(self.request('/api/admin/session', token=token)[1], {'admin': False})


if __name__ == '__main__':
    unittest.main()
