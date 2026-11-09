from datetime import datetime, timezone

from fastapi.testclient import TestClient

import api
from database import Analysis, User, session


def test_history_pagination_keeps_account_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'history.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-only-signing-key-with-32-bytes")

    with TestClient(api.app) as client:
        credentials = {"username": "history_owner", "password": "example-password"}
        assert client.post("/api/user/register", json=credentials).status_code == 200
        token = client.post("/api/user/login", json=credentials).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with session() as db:
            owner = db.query(User).filter_by(username="history_owner").one()
            other = User(username="history_other", password_hash=owner.password_hash)
            db.add(other)
            db.flush()
            db.add_all(
                Analysis(
                    id=f"record-{number}",
                    owner_id=owner.id if number < 3 else other.id,
                    filename=f"{number}.jpg",
                    created_at=created_at,
                    status="queued",
                    note="",
                )
                for number in range(4)
            )
            db.commit()

        def history(**params):
            response = client.get("/api/analysis/list", params=params, headers=headers)
            assert response.status_code == 200
            body = response.json()
            assert body["code"] == 200 and body["message"] == "success"
            return body["data"]

        first = history(page=1, pageSize=2)
        assert [row["id"] for row in first["list"]] == ["record-2", "record-1"]
        assert first["total"] == 3 and first["hasMore"] is True
        assert first["list"][0]["yolo"] is None and first["list"][0]["doubao"] is None

        second = history(page=2, pageSize=2)
        assert [row["id"] for row in second["list"]] == ["record-0"]
        assert second["total"] == 3 and second["hasMore"] is False

        assert history(page=3, pageSize=2)["list"] == []
        assert history()["total"] == 3

        for params in ({"page": 0}, {"pageSize": 101}, {"pageSize": 0}):
            invalid = client.get("/api/analysis/list", params=params, headers=headers)
            assert invalid.status_code == 422
            assert invalid.json()["code"] == 422
