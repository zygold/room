"""auth router 基础测试: login / me / logout / change-password."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import database
    import routers.auth as ar
    database.DB_PATH = str(tmp_path / "test.db")
    database.init_db()  # 建表 + seed admin
    ar.SESSIONS.clear()
    from main import app
    c = TestClient(app)
    yield c
    ar.SESSIONS.clear()


class TestAuth:
    def test_login_ok(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.text
        assert "token" in r.cookies

    def test_login_bad_password(self, client):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code in (401, 403)

    def test_login_bad_user(self, client):
        r = client.post("/api/auth/login", json={"username": "nouser", "password": "x"})
        assert r.status_code in (401, 403)

    def test_me_after_login(self, client):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        r = client.get("/api/auth/me")
        assert r.status_code == 200, r.text

    def test_change_password_flow(self, client):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        r = client.post("/api/auth/change-password",
                        json={"old_password": "admin123", "new_password": "admin999"})
        assert r.status_code == 200, r.text
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code in (401, 403)
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin999"})
        assert r.status_code == 200
        r = client.post("/api/auth/change-password",
                        json={"old_password": "admin999", "new_password": "admin123"})
        assert r.status_code == 200

    def test_change_password_wrong_old(self, client):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        r = client.post("/api/auth/change-password",
                        json={"old_password": "hacked", "new_password": "xxx"})
        assert r.status_code == 400

    def test_change_password_too_short(self, client):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        r = client.post("/api/auth/change-password",
                        json={"old_password": "admin123", "new_password": "ab"})
        assert r.status_code == 400

    def test_logout(self, client):
        client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        r = client.post("/api/auth/logout")
        assert r.status_code == 200
