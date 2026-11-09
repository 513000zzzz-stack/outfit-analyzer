import logging
import os
import shutil
from pathlib import Path
from time import perf_counter

from database import Analysis, session, storage
from outfit_api.crud.analyses import claim
from outfit_api.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)


def run_yolo(source, output_dir, device):
    from inference.model_test import predicted_image

    # 推理脚本在同名目录已存在时会另建 yolo_2，而接口只认 yolo/detection.jpg，
    # 所以重跑前先清空这一路的输出目录，保证结果落在约定位置。
    shutil.rmtree(Path(output_dir), ignore_errors=True)
    return predicted_image(source, output_dir=output_dir, device=device, verbose=False)


def run_doubao(source, output_dir):
    from inference.ai_analysis import analyze_outfit

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
    # queued 直接认领；Worker 被强杀后重新投递的 running 记录，只有超时才会再次认领。
    with session() as db:
        if not claim(db, analysis_id):
            logger.info("任务 %s 已被处理、仍在执行或不存在，跳过", analysis_id)
            return

    logger.info("任务 %s 开始分析", analysis_id)
    folder = storage() / analysis_id
    source = folder / "input.jpg"
    yolo = run_branch(
        "YOLO", lambda: run_yolo(source, folder / "yolo", os.getenv("YOLO_DEVICE", "cpu"))
    )
    with session() as db:
        item = db.get(Analysis, analysis_id)
        item.yolo = yolo
        db.commit()
    logger.info("任务 %s YOLO %s %.2fs", analysis_id, yolo["status"], yolo["seconds"])

    doubao = run_branch("豆包", lambda: run_doubao(source, folder / "doubao"))
    successful = sum(result["status"] == "ok" for result in (yolo, doubao))
    status = ("failed", "partial", "completed")[successful]
    with session() as db:
        item = db.get(Analysis, analysis_id)
        item.doubao = doubao
        item.status = status
        db.commit()
    logger.info(
        "任务 %s 结束 status=%s 豆包 %s %.2fs",
        analysis_id, status, doubao["status"], doubao["seconds"],
    )


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
