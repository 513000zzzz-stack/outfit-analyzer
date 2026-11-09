from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import api
import jobs
from database import Analysis, User, session


def _login(client, username):
    payload = {"username": username, "password": "strong-password"}
    assert client.post("/api/user/register", json=payload).status_code == 200
    body = client.post("/api/user/login", json=payload).json()
    return {"Authorization": f"Bearer {body['data']['token']}"}


def _fake_branches(monkeypatch):
    monkeypatch.setattr(
        jobs, "run_yolo",
        lambda source, output_dir, device: {"objects": [], "color_analysis": {}, "limitations": []},
    )
    monkeypatch.setattr(jobs, "run_doubao", lambda source, output_dir: {"answer": "ok"})


def _configure(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-signing-key-with-at-least-32-bytes")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")


def test_worker_reclaims_stale_running_but_not_fresh_running(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _fake_branches(monkeypatch)
    now = datetime.now(timezone.utc)

    with TestClient(api.app) as client:
        _login(client, "recovery_owner")
        with session() as db:
            owner = db.query(User).filter_by(username="recovery_owner").one()
            db.add_all([
                Analysis(
                    id="stale-running", owner_id=owner.id, filename="a.jpg",
                    created_at=now - timedelta(minutes=40),
                    started_at=now - timedelta(minutes=30), status="running", note="",
                ),
                Analysis(
                    id="fresh-running", owner_id=owner.id, filename="b.jpg",
                    created_at=now, started_at=now, status="running", note="",
                ),
            ])
            db.commit()

        jobs.process_analysis("stale-running")
        jobs.process_analysis("fresh-running")

        with session() as db:
            stale = db.get(Analysis, "stale-running")
            fresh = db.get(Analysis, "fresh-running")
            assert stale.status == "completed"
            assert stale.yolo["status"] == "ok" and stale.doubao["status"] == "ok"
            # 刚被别的 Worker 认领的记录不能被抢走，避免重复调用模型。
            assert fresh.status == "running"
            assert fresh.yolo is None and fresh.doubao is None


def test_startup_sweep_marks_stale_records(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)

    with TestClient(api.app) as client:
        _login(client, "sweep_owner")
        with session() as db:
            owner = db.query(User).filter_by(username="sweep_owner").one()
            db.add_all([
                Analysis(
                    id="stale-queued", owner_id=owner.id, filename="c.jpg",
                    created_at=now - timedelta(hours=2), status="queued", note="",
                ),
                Analysis(
                    id="fresh-queued", owner_id=owner.id, filename="d.jpg",
                    created_at=now, status="queued", note="",
                ),
                Analysis(
                    id="legacy-running", owner_id=owner.id, filename="e.jpg",
                    created_at=now - timedelta(hours=1), started_at=None,
                    status="running", note="",
                ),
                Analysis(
                    id="partial-running", owner_id=owner.id, filename="f.jpg",
                    created_at=now - timedelta(hours=1),
                    started_at=now - timedelta(minutes=30), status="running", note="",
                    yolo={"status": "ok", "seconds": 1.0, "data": {"objects": []}},
                ),
            ])
            db.commit()

    # 下一次启动会执行清扫。
    with TestClient(api.app):
        with session() as db:
            assert db.get(Analysis, "stale-queued").status == "failed"
            assert db.get(Analysis, "fresh-queued").status == "queued"
            assert db.get(Analysis, "legacy-running").status == "failed"
            # 已经有成功分支的记录保留结果，落为 partial。
            assert db.get(Analysis, "partial-running").status == "partial"
            assert db.get(Analysis, "partial-running").doubao["status"] == "error"
