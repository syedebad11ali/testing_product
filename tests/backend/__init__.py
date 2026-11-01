"""Backend test package.

Flask serves static pages with ``send_file``: the response holds the file open until the response is closed. The test client does not
close responses it hands back, which produced one ``ResourceWarning: unclosed file`` per static request (index.html, login.html, ...).
Reading the response completely (``buffered=True``) closes the file; status, headers and body are identical, so what the tests verify
is unchanged. Set here once because every backend test module imports this package first.
"""
import functools

from flask import Flask
from flask.testing import FlaskClient


class BufferedClient(FlaskClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Every request (get/post/...) goes through self.open; a per-call ``buffered=...`` still overrides this default.
        self.open = functools.partial(self.open, buffered=True)


Flask.test_client_class = BufferedClient
