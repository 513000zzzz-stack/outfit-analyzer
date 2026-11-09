from fastapi.testclient import TestClient

from api import app


def test_unified_response_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'envelope.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-only-signing-key-at-least-32-bytes")

    with TestClient(app) as client:
        unauthorized = client.get("/api/analysis/list")
        assert unauthorized.status_code == 401
        assert unauthorized.headers["WWW-Authenticate"] == "Bearer"
        assert unauthorized.json() == {"code": 401, "message": "请重新登录", "data": None}

        credentials = {"username": "envelope_owner", "password": "example-password"}
        registered = client.post("/api/user/register", json=credentials)
        assert registered.status_code == 200
        body = registered.json()
        assert body["code"] == 200 and body["message"] == "注册成功"
        assert body["data"]["userInfo"]["username"] == "envelope_owner"
        token = client.post("/api/user/login", json=credentials).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        profile = client.get("/api/user/info", headers=headers).json()
        assert profile["code"] == 200 and profile["message"] == "success"
        assert profile["data"]["username"] == "envelope_owner"
        assert profile["data"]["bio"] == "这个人很懒，什么都没留下"
        assert profile["data"]["avatar"] == ""

        empty = client.get("/api/analysis/list", headers=headers).json()
        assert empty == {
            "code": 200,
            "message": "success",
            "data": {"list": [], "total": 0, "hasMore": False},
        }

        invalid = client.get("/api/analysis/list", params={"pageSize": 101}, headers=headers)
        assert invalid.status_code == 422
        assert invalid.json()["code"] == 422
        assert invalid.json()["data"][0]["loc"][-1] == "pageSize"

        assert client.get("/api/analysis/detail/missing", headers=headers).json() == {
            "code": 404,
            "message": "找不到这条分析记录",
            "data": None,
        }

        # 旧路径已经下线，避免同时存在两套接口。
        assert client.get("/analyses", headers=headers).status_code == 404
        assert client.get("/api/v1/analyses", headers=headers).status_code == 404
