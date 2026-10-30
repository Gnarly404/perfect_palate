import os
import re
import smtplib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import bcrypt
import database
from app import app
from test_support import CsrfTestClient

app.test_client_class = CsrfTestClient


class PasswordRecoveryEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = database.DATABASE
        database.DATABASE = os.path.join(self.temp_dir.name, 'test.db')
        database.init_db()
        self.original_public_base_url = app.config['PUBLIC_BASE_URL']
        app.config['PUBLIC_BASE_URL'] = 'https://perfect-palate.example'
        self.client = app.test_client()

        conn = database.get_db_connection()
        conn.execute(
            'INSERT INTO users (email, password_hash) VALUES (?, ?)',
            ('user@example.com', 'old-hash')
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        app.config['PUBLIC_BASE_URL'] = self.original_public_base_url
        database.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def test_forgot_password_page_exists(self):
        response = self.client.get('/forgot-password')
        self.assertEqual(response.status_code, 200)

    def test_reset_password_page_exists_for_token(self):
        response = self.client.get('/reset-password/token123')
        self.assertEqual(response.status_code, 200)

    def test_request_emails_reset_link_and_resets_password(self):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp_factory = MagicMock()
        smtp_factory.return_value.__enter__.return_value = smtp

        smtp_env = {
            'SMTP_HOST': 'smtp.example.com',
            'SMTP_PORT': '587',
            'SMTP_USERNAME': 'mailer@example.com',
            'SMTP_PASSWORD': 'test-password',
            'SMTP_FROM_EMAIL': 'mailer@example.com',
        }
        with patch.dict(os.environ, smtp_env), patch('app.smtplib.SMTP', smtp_factory):
            response = self.client.post(
                '/forgot-password',
                json={'email': 'USER@example.com'},
            )

        self.assertEqual(response.status_code, 200)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with('mailer@example.com', 'test-password')
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'user@example.com')
        self.assertIn('Reset your Perfect Palate password', message['Subject'])

        body = message.get_body(preferencelist=('plain',)).get_content()
        match = re.search(r'https://perfect-palate\.example/reset-password/([A-Za-z0-9_-]+)', body)
        self.assertIsNotNone(match)
        token = match.group(1)

        reset_response = self.client.post(
            f'/reset-password/{token}',
            json={'password': 'new-password'},
        )
        self.assertEqual(reset_response.status_code, 200)
        conn = database.get_db_connection()
        password_hash = conn.execute(
            'SELECT password_hash FROM users WHERE email = ?',
            ('user@example.com',),
        ).fetchone()['password_hash']
        conn.close()
        self.assertTrue(password_hash.startswith('$2'))
        self.assertTrue(bcrypt.checkpw(b'new-password', password_hash.encode('ascii')))

        reused_response = self.client.post(
            f'/reset-password/{token}',
            json={'password': 'another-password'},
        )
        self.assertEqual(reused_response.status_code, 400)

    def test_smtp_failure_returns_error_and_invalidates_reset_link(self):
        smtp = MagicMock()
        smtp.send_message.side_effect = smtplib.SMTPConnectError(421, b'Service unavailable')
        smtp_factory = MagicMock()
        smtp_factory.return_value.__enter__.return_value = smtp

        smtp_env = {
            'SMTP_HOST': 'smtp.example.com',
            'SMTP_PORT': '587',
            'SMTP_FROM_EMAIL': 'mailer@example.com',
        }
        with patch.dict(os.environ, smtp_env), patch('app.smtplib.SMTP', smtp_factory):
            with self.assertLogs('app', level='ERROR'):
                response = self.client.post(
                    '/forgot-password',
                    json={'email': 'user@example.com'},
                )

        self.assertEqual(response.status_code, 503)
        conn = database.get_db_connection()
        token = conn.execute(
            'SELECT token, used_at FROM password_reset_tokens'
        ).fetchone()
        conn.close()
        self.assertIsNotNone(token)
        self.assertIsNotNone(token['used_at'])

    def test_missing_smtp_configuration_returns_service_error(self):
        with patch.dict(os.environ, {'SMTP_HOST': '', 'SMTP_FROM_EMAIL': ''}):
            with self.assertLogs('app', level='ERROR'):
                response = self.client.post(
                    '/forgot-password',
                    json={'email': 'user@example.com'},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['status'], 'error')


if __name__ == '__main__':
    unittest.main()
