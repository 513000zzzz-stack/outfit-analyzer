from pathlib import Path

from ultralytics import YOLO


def resume_train():
    ##读取已经保存的训练进度
    project_dir = Path(__file__).resolve().parents[1]
    checkpoint = project_dir / "runs" / "detect" / "fashion_yolo26n" / "weights" / "last.pt"
    model = YOLO(str(checkpoint))

    ##从保存的位置继续训练
    model.train(resume=True)


if __name__ == "__main__":
    resume_train()