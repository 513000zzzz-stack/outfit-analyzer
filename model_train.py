from pathlib import Path

import torch
from ultralytics import YOLO

def train_model():
    ##设置路径
    project_dir=Path(r"D:\考核2\outfit-analyzer")
    data_file = project_dir / "data" / "yolo" / "data.yaml"
    weight_file = project_dir / "yolo26n.pt"

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

    ##开始训练
    model.train(
        data=str(data_file),
        epochs=150,
        patience=40,
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



