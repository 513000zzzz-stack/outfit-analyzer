from pathlib import Path

import torch
from ultralytics import YOLO
import logging
from ultralytics.utils import LOGGER
project_dir=Path(__file__).resolve().parents[1]
def log_add(trainer):
    ##使用YOLO本次训练的实际结果目录
    log_file = Path(trainer.save_dir) / "train_utf8.log"

    ##同一个日志文件已经有处理器时，不重复添加
    for handler in LOGGER.handlers:
        if isinstance(handler, logging.FileHandler):
            if Path(handler.baseFilename) == log_file:
                trainer.file_log_handler = handler
                return

    ##追加保存本次任务的日志
    file_handler = logging.FileHandler(
        log_file,
        mode="a",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    LOGGER.addHandler(file_handler)

    ##记住本次使用的处理器，结束时关闭
    trainer.file_log_handler = file_handler

    LOGGER.info("==========本次训练日志开始==========")
    LOGGER.info(f"日志保存位置：{log_file}")
    LOGGER.info(f"本次训练参数：{vars(trainer.args)}")


def log_close(trainer):
    ##本次任务结束后关闭处理器，避免下个任务继续写入旧文件
    handler = getattr(trainer, "file_log_handler", None)

    if handler is not None:
        LOGGER.removeHandler(handler)
        handler.close()
        trainer.file_log_handler = None
def train_model():
    ##设置路径
    data_file = project_dir / "data" / "yolo" / "data.yaml"
    weight_file = project_dir / "models" / "yolo26n.pt"

    ##检查数据配置
    if not data_file.is_file():
        raise FileExistsError(
            f"找不到数据配置文件：{data_file}"
        )
##检查显卡
    if not torch.cuda.is_available():
        raise RuntimeError(
            "当前Python环境无法使用显卡，请检查是否选择了outfit环境"
        )

    print("使用显卡：", torch.cuda.get_device_name(0))
    print("数据配置：", data_file)

    ##加载预训练模型
    #首次运行时，如果本地没有权重，会尝试自动下载
    model=YOLO(str(weight_file))
    model = YOLO(str(weight_file))

    ##YOLO确定结果目录后，自动开启日志
    model.add_callback("on_pretrain_routine_start", log_add)

    ##训练退出时，自动关闭本次文件处理器
    model.add_callback("teardown", log_close)

    ##开始训练
    model.train(
        data=str(data_file),
        epochs=1,
        patience=1,
        imgsz=960,
        batch=-1,
        device=0,
        amp=True,
        workers=4,
        optimizer="auto",
        lr0=0.001,
        seed=42,
        close_mosaic=15,
        val=True,
        save=True,
        plots=True,
        cache=False,
        project=str(project_dir / "runs" / "detect"),
        name="fashion_yolo26n",
    )
    ##显示训练结果位置
    save_dir = Path(model.trainer.save_dir)

    print("\n训练结束")
    print("结果目录：", save_dir)
    print("最佳模型：", save_dir / "weights" / "best.pt")
    print("最后一轮模型：", save_dir / "weights" / "last.pt")


if __name__ == "__main__":
    train_model()



