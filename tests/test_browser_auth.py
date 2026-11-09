from fastapi.testclient import TestClient

from api import app


def test_browser_authentication_and_account_router_share_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'browser.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-only-signing-key-at-least-32-bytes")
    origin = "http://localhost:8080"
    account = {"username": "browser_owner", "password": "example-password"}

    with TestClient(app, base_url=origin) as client:
        assert client.post("/api/user/register", json=account).status_code == 200
        login_url = "/browser-auth/login"
        assert client.get(login_url).status_code == 200
        assert client.post(login_url, data=account, headers={"Origin": "http://other.invalid"}).status_code == 403
        login = client.post(login_url, data=account, headers={"Origin": origin}, follow_redirects=False)
        assert login.status_code == 303 and login.headers["location"] == "/"
        assert "HttpOnly" in login.headers["set-cookie"]
        token = client.cookies["outfit_token"]
        headers = {"Authorization": f"Bearer {token}"}
        profile = client.get("/api/user/info", headers=headers).json()
        assert profile["code"] == 200
        assert profile["data"]["username"] == "browser_owner"
        assert client.get("/api/user/info").status_code == 401
        logout = client.post("/browser-auth/logout", headers={"Origin": origin}, follow_redirects=False)
        assert logout.status_code == 303
        assert "Max-Age=0" in logout.headers["set-cookie"]
        assert "outfit_token" not in client.cookies
