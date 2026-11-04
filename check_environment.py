import sys

import torch
import ultralytics
from ultralytics import YOLO


def main():
    print("Python 路径：", sys.executable)
    print("Python 版本：", sys.version.split()[0])
    print("PyTorch 版本：", torch.__version__)
    print("Ultralytics 版本：", ultralytics.__version__)
    print("YOLO 类导入成功：", YOLO.__name__)

    cuda_available = torch.cuda.is_available()
    print("CUDA 是否可用：", cuda_available)

    if cuda_available:
        print("显卡名称：", torch.cuda.get_device_name(0))

        # 在显卡上创建三个数字，分别都是 1。
        x = torch.ones(3, device="cuda")

        # 在显卡上进行乘法，再将结果传回 CPU。
        result = (x * 2).cpu().tolist()
        print("显卡计算结果：", result)
    else:
        print("当前环境未启用 GPU，请先检查解释器和 PyTorch。")


if __name__ == "__main__":
    main()