from werkzeug.datastructures import Headers
from flask.testing import FlaskClient


class CsrfTestClient(FlaskClient):
    """Include a valid CSRF token in ordinary test requests, unless overridden."""

    def open(self, *args, **kwargs):
        method = (kwargs.get('method') or 'GET').upper()
        if method not in {'GET', 'HEAD', 'OPTIONS', 'TRACE'}:
            headers = Headers(kwargs.get('headers'))
            if 'X-CSRF-Token' not in headers:
                with self.session_transaction() as session:
                    token = session.setdefault('_csrf_token', 'test-csrf-token')
                headers['X-CSRF-Token'] = token
                kwargs['headers'] = headers
        return super().open(*args, **kwargs)
