import logging
import os
from time import perf_counter

from sqlalchemy import update

from database import Analysis, session, storage

logger = logging.getLogger(__name__)


def run_yolo(source, output_dir, device):
    from model_test import predicted_image

    return predicted_image(source, output_dir=output_dir, device=device, verbose=False)


def run_doubao(source, output_dir):
    from ai_analysis import analyze_outfit

    return analyze_outfit(source, output_dir=output_dir, verbose=False)


def run_branch(label, task):
    started = perf_counter()
    try:
        data = task()
        # 结果通过 API 返回。原始本地路径、提示词和请求标识留在内部文件。
        keys = (
            ("objects", "color_analysis", "limitations")
            if label == "YOLO"
            else ("answer", "request_seconds", "usage", "returned_model", "finish_reason")
        )
        return {
            "status": "ok",
            "seconds": round(perf_counter() - started, 3),
            "data": {key: data[key] for key in keys if key in data},
        }
    except Exception:
        logger.exception("%s 分析失败", label)
        return {
            "status": "error",
            "seconds": round(perf_counter() - started, 3),
            "error": f"{label} 分析失败，请查看 Worker 日志和运行配置。",
        }


def process_analysis(analysis_id):
    # 仅当记录仍在排队时认领，重复投递不会重复调用模型。
    with session() as db:
        claimed = db.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id, Analysis.status == "queued")
            .values(status="running")
        )
        db.commit()
        if claimed.rowcount != 1:
            return

    folder = storage() / analysis_id
    source = folder / "input.jpg"
    yolo = run_branch(
        "YOLO", lambda: run_yolo(source, folder / "yolo", os.getenv("YOLO_DEVICE", "cpu"))
    )
    with session() as db:
        item = db.get(Analysis, analysis_id)
        item.yolo = yolo
        db.commit()

    doubao = run_branch("豆包", lambda: run_doubao(source, folder / "doubao"))
    successful = sum(result["status"] == "ok" for result in (yolo, doubao))
    with session() as db:
        item = db.get(Analysis, analysis_id)
        item.doubao = doubao
        item.status = ("failed", "partial", "completed")[successful]
        db.commit()


def job_failed(job, connection, exc_type, exc_value, traceback):
    with session() as db:
        item = db.get(Analysis, job.args[0])
        if item and item.status in {"queued", "running"}:
            error = {"status": "error", "error": "任务被中断，请查看 Worker 日志。"}
            item.yolo = item.yolo or error
            item.doubao = item.doubao or error
            item.status = "partial" if any(
                result["status"] == "ok" for result in (item.yolo, item.doubao)
            ) else "failed"
            db.commit()
