"""
Konbit — Erè 500 yo kenbe header CORS yo (sinon frontend lan kwè sèvè a pa reponn)
Chemen: backend/tests/test_errors.py
"""

import asyncio

from starlette.requests import Request

from app.main import origins, unhandled_exception_handler


def _request(origin=None) -> Request:
    headers = [(b"origin", origin.encode())] if origin else []
    return Request({
        "type": "http", "method": "GET", "path": "/api/x", "raw_path": b"/api/x",
        "query_string": b"", "headers": headers, "scheme": "http",
        "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "root_path": "",
    })


def _call(origin=None):
    return asyncio.run(unhandled_exception_handler(_request(origin), RuntimeError("boom")))


def test_500_keeps_cors_for_known_frontend():
    resp = _call(origins[0])
    assert resp.status_code == 500
    assert resp.headers["access-control-allow-origin"] == origins[0]
    assert resp.headers["access-control-allow-credentials"] == "true"


def test_500_gives_nothing_to_unknown_origin():
    resp = _call("https://move-sit.example")
    assert resp.status_code == 500
    assert "access-control-allow-origin" not in resp.headers
    assert "access-control-allow-origin" not in _call(None).headers