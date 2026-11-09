import io

from fastapi.testclient import TestClient
from fakeredis import FakeRedis
from PIL import Image
from rq import Queue


def test_upload_queue_partial_result_and_ownership(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-signing-key-with-at-least-32-bytes")
    monkeypatch.setenv("REDIS_URL", "redis://test:6379/0")
    import api
    import jobs
    from outfit_api.services import analyses

    broker = FakeRedis()
    queue = Queue("outfit", connection=broker)
    monkeypatch.setattr(analyses.Redis, "from_url", lambda *args, **kwargs: broker)

    def yolo(source, output_dir, device):
        output_dir.mkdir()
        (output_dir / "detection.jpg").write_bytes(source.read_bytes())
        return {"objects": [], "color_analysis": {}, "limitations": []}

    def unavailable(source, output_dir):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(jobs, "run_yolo", yolo)
    monkeypatch.setattr(jobs, "run_doubao", unavailable)
    with TestClient(api.app) as client:
        def login(username):
            payload = {"username": username, "password": "strong-password"}
            assert client.post("/api/user/register", json=payload).status_code == 200
            body = client.post("/api/user/login", json=payload).json()
            assert body["code"] == 200 and body["message"] == "登录成功"
            return {"Authorization": f"Bearer {body['data']['token']}"}

        owner, other = login("owner"), login("other")
        unauthorized = client.get("/api/analysis/list")
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"code": 401, "message": "请重新登录", "data": None}
        invalid = client.post(
            "/api/analysis/create", headers=owner, files={"image": ("broken.png", b"not image")}
        )
        assert invalid.status_code == 415
        assert invalid.json()["code"] == 415
        assert queue.count == 0
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "#c18766").save(image, "PNG")
        response = client.post(
            "/api/analysis/create", headers=owner, files={"image": ("outfit.png", image.getvalue())}
        )
        assert response.status_code == 202
        envelope = response.json()
        assert envelope["code"] == 202 and envelope["message"] == "任务已创建"
        record = envelope["data"]
        route = f"/api/analysis/detail/{record['id']}"
        assert record["status"] == "queued" and queue.job_ids == [record["id"]]
        deleted = client.delete(f"/api/analysis/delete/{record['id']}", headers=owner)
        assert deleted.status_code == 409
        assert deleted.json()["code"] == 409
        assert client.get(route, headers=other).status_code == 404
        assert client.get(f"/api/analysis/file/{record['id']}/input.jpg", headers=other).status_code == 404
        assert client.get("/api/analysis/list", headers=other).json()["data"]["list"] == []

        job, _ = Queue.dequeue_any([queue], timeout=None, connection=broker)
        assert job.id == record["id"]
        job.perform()
        result = client.get(route, headers=owner).json()["data"]
        assert result["status"] == "partial"
        assert result["yolo"]["status"] == "ok"
        assert result["doubao"]["status"] == "error"
        assert client.get(f"/api/analysis/file/{record['id']}/detection.jpg", headers=owner).status_code == 200
        edited = client.put(f"/api/analysis/note/{record['id']}", headers=owner, json={"note": "对比记录"})
        assert edited.json()["data"]["note"] == "对比记录"
        removed = client.delete(f"/api/analysis/delete/{record['id']}", headers=owner)
        assert removed.status_code == 200
        assert removed.json() == {"code": 200, "message": "删除成功", "data": None}
        assert client.get(route, headers=owner).status_code == 404
