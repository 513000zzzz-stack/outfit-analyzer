from ultralytics import YOLO


def resume_train():
    ##读取已经保存的训练进度
    model = YOLO(
        r"D:\考核2\outfit-analyzer\runs\detect"
        r"\fashion_yolo26n\weights\last.pt"
    )

    ##从保存的位置继续训练
    model.train(resume=True)


if __name__ == "__main__":
    resume_train()