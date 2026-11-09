import json
from pathlib import Path
import shutil
import math
import ijson
from PIL import Image, ImageDraw

def convert_labels(annotation_file, label_output_dir):
    ##读取全部类别
    with annotation_file.open("rb") as file:
        categories = next(ijson.items(file, "categories"))

    categories.sort(key=lambda category: category["id"])

    if len(categories) != 46:
        raise ValueError("读取到的类别数量不是46，请检查标注文件")

    #全部类别保留，只建立YOLO编号
    category_mapping = {}

    for index, category in enumerate(categories):
        category_mapping[category["id"]] = index

    ##读取图片信息
    with annotation_file.open("rb") as file:
        images = next(ijson.items(file, "images"))

    #按图片编号保存图片信息和标签内容
    image_info_by_id = {}
    label_lines_by_id = {}

    for image_info in images:
        image_id = image_info["id"]
        image_info_by_id[image_id] = image_info
        label_lines_by_id[image_id] = []

    ##逐条读取标注并转换坐标
    total_count = 0
    valid_count = 0
    invalid_count = 0

    print(f"\n开始转换：{annotation_file.name}")

    with annotation_file.open("rb") as file:
        for annotation in ijson.items(file, "annotations.item"):
            total_count += 1

            if total_count % 50000 == 0:
                print(f"已读取：{total_count}条标注")

            image_id = annotation["image_id"]
            category_id = annotation["category_id"]
            image_info = image_info_by_id[image_id]

            image_width = int(image_info["width"])
            image_height = int(image_info["height"])

            #原始框格式为：左上角x、左上角y、宽度、高度
            box = annotation["bbox"]

            if len(box) != 4:
                invalid_count += 1
                continue

            x, y, width, height = map(float, box)

            #过滤无效尺寸和无效数字，不删除任何类别
            if (
                image_width <= 0
                or image_height <= 0
                or width <= 0
                or height <= 0
                or not all(
                    math.isfinite(value)
                    for value in (x, y, width, height)
                )
            ):
                invalid_count += 1
                continue

            #将超出图片边界的部分裁回图片范围
            x1 = max(0.0, min(image_width, x))
            y1 = max(0.0, min(image_height, y))
            x2 = max(0.0, min(image_width, x + width))
            y2 = max(0.0, min(image_height, y + height))

            if x2 <= x1 or y2 <= y1:
                invalid_count += 1
                continue

            #转换成YOLO需要的中心坐标和宽高比例
            x_center = (x1 + x2) / 2 / image_width
            y_center = (y1 + y2) / 2 / image_height
            box_width = (x2 - x1) / image_width
            box_height = (y2 - y1) / image_height

            yolo_category_id = category_mapping[category_id]

            line = (
                f"{yolo_category_id} "
                f"{x_center:.10f} {y_center:.10f} "
                f"{box_width:.10f} {box_height:.10f}"
            )

            label_lines_by_id[image_id].append(line)
            valid_count += 1

    ##为每张图片生成同名txt
    label_output_dir.mkdir(parents=True, exist_ok=True)

    for image_info in images:
        image_id = image_info["id"]
        image_stem = Path(image_info["file_name"]).stem
        label_file = label_output_dir / (image_stem + ".txt")

        lines = label_lines_by_id[image_id]
        content = "\n".join(lines)

        if lines:
            content += "\n"

        label_file.write_text(content, encoding="utf-8")

    ##显示转换结果
    print("类别数量：", len(categories))
    print("标签文件数量：", len(images))
    print("有效标注数量：", valid_count)
    print("跳过的无效框数量：", invalid_count)

    return categories


def draw_label_previews(image_dir, label_dir, output_dir, categories):
    ##生成少量检查图
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_count = 0

    for image_path in sorted(image_dir.iterdir()):
        if not image_path.is_file():
            continue

        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue

        label_file = label_dir / (image_path.stem + ".txt")

        if not label_file.is_file():
            continue

        lines = label_file.read_text(encoding="utf-8").splitlines()

        if not lines:
            continue

        ##打开图片
        with Image.open(image_path) as original:
            image = original.convert("RGB")

        image_width, image_height = image.size
        draw = ImageDraw.Draw(image)

        ##从生成的txt中读取标签，反算位置并画框
        for line in lines:
            category_id, cx, cy, width, height = line.split()

            category_id = int(category_id)
            cx, cy, width, height = map(
                float, (cx, cy, width, height)
            )

            x1 = (cx - width / 2) * image_width
            y1 = (cy - height / 2) * image_height
            x2 = (cx + width / 2) * image_width
            y2 = (cy + height / 2) * image_height

            draw.rectangle(
                (x1, y1, x2, y2),
                outline="red",
                width=2,
            )

            category_name = categories[category_id]["name"]
            draw.text(
                (max(0, x1), max(0, y1)),
                category_name,
                fill="red",
            )

        ##另存检查图，原图不修改
        image.thumbnail((1200, 1200))
        image.save(output_dir / (image_path.stem + ".jpg"))

        preview_count += 1

        if preview_count >= 5:
            break

    print("检查图保存到：", output_dir)
def datapro():
    ##设置路径
    project_dir = Path(__file__).resolve().parents[1]

    #训练图片所在的位置
    train_image_dir = project_dir / "train2020" / "train"

    #训练集的标注文件
    train_annotation_file = (
        project_dir
        / "fashionpedia-detection-annotations"
        / "instances_attributes_train2020.json"
    )

    #验证和测试图片混在这个目录中
    mixed_image_dir = project_dir / "val_test2020" / "test"

    #验证集标注，里面包含验证图片的文件名
    val_annotation_file = (
        project_dir
        / "fashionpedia-detection-annotations"
        / "instances_attributes_val2020.json"
    )

    #整理后的图片保存位置
    train_output_dir = project_dir / "data" / "yolo" / "images" / "train"
    val_output_dir = project_dir / "data" / "yolo" / "images" / "val"
    test_output_dir = project_dir / "data" / "yolo" / "images" / "test"

    ##检查路径
    print("训练图片目录：", train_image_dir)
    print("图片目录存在：", train_image_dir.is_dir())
    print("训练标注文件：", train_annotation_file)
    print("标注文件存在：", train_annotation_file.is_file())

    if not train_image_dir.is_dir():
        raise FileNotFoundError(
            f"找不到训练图片目录：{train_image_dir}"
        )

    if not train_annotation_file.is_file():
        raise FileNotFoundError(
            f"找不到训练标注：{train_annotation_file}"
        )

    if not mixed_image_dir.is_dir():
        raise FileNotFoundError(
            f"找不到混合图片目录：{mixed_image_dir}"
        )

    if not val_annotation_file.is_file():
        raise FileNotFoundError(
            f"找不到验证标注：{val_annotation_file}"
        )

    ##读取验证图片名单
    with val_annotation_file.open("r", encoding="utf-8") as file:
        val_data = json.load(file)

    val_image_names = set()

    for image_info in val_data["images"]:
        image_name = Path(image_info["file_name"]).name
        val_image_names.add(image_name)

    print("\n验证名单中的图片数量：", len(val_image_names))

    ##收集本地图片，检查是否缺图
    image_paths = []
    local_image_names = set()

    for image_path in mixed_image_dir.iterdir():
        if image_path.is_file():
            if image_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                image_paths.append(image_path)
                local_image_names.add(image_path.name)

    missing_val_names = val_image_names - local_image_names

    if missing_val_names:
        raise FileNotFoundError(
            f"有 {len(missing_val_names)} 张验证图片未找到，"
            "请检查图片目录。"
        )

    ##创建输出目录
    train_output_dir.mkdir(parents=True, exist_ok=True)
    val_output_dir.mkdir(parents=True, exist_ok=True)
    test_output_dir.mkdir(parents=True, exist_ok=True)

    ##分别复制验证和测试图片
    val_count = 0
    test_count = 0

    print("\n开始整理验证和测试图片……")

    for image_path in image_paths:
        image_name = image_path.name

        if image_name in val_image_names:
            target_dir = val_output_dir
            val_count += 1
        else:
            target_dir = test_output_dir
            test_count += 1

        target_path = target_dir / image_name

        #已经复制过的同名文件跳过，方便重复运行
        if not target_path.exists():
            shutil.copy2(image_path, target_path)

    ##复制训练图片
    train_count = 0
    copied_train_count = 0

    print("\n开始整理训练图片……")

    for image_path in train_image_dir.iterdir():
        if image_path.is_file():
            if image_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                target_path = train_output_dir / image_path.name

                #尚未复制过的图片，才进行复制
                if not target_path.exists():
                    shutil.copy2(image_path, target_path)
                    copied_train_count += 1

                #无论是否需要复制，都计入训练图片总数
                train_count += 1

                #每检查1000张图片，显示一次进度
                if train_count % 1000 == 0:
                    print(f"已检查训练图片：{train_count} 张")

    ##显示图片整理结果
    print("\n图片整理完成")
    print("训练图片数量：", train_count)
    print("本次新增复制的训练图片：", copied_train_count)
    print("验证图片数量：", val_count)
    print("测试图片数量：", test_count)

    ##设置标签输出目录
    yolo_dir = project_dir / "data" / "yolo"
    train_label_dir = yolo_dir / "labels" / "train"
    val_label_dir = yolo_dir / "labels" / "val"

    ##转换训练集标签
    train_categories = convert_labels(
        train_annotation_file,
        train_label_dir,
    )

    ##转换验证集标签
    val_categories = convert_labels(
        val_annotation_file,
        val_label_dir,
    )

    ##检查训练与验证的类别是否一致
    train_definitions = [
        (category["id"], category["name"])
        for category in train_categories
    ]

    val_definitions = [
        (category["id"], category["name"])
        for category in val_categories
    ]

    if train_definitions != val_definitions:
        raise ValueError("训练集与验证集的类别定义不一致")

    ##生成YOLO配置文件
    yaml_lines = [
        "path: " + json.dumps(yolo_dir.as_posix(), ensure_ascii=False),
        "train: images/train",
        "val: images/val",
        "names:",
    ]

    for index, category in enumerate(train_categories):
        category_name = json.dumps(
            category["name"],
            ensure_ascii=False,
        )
        yaml_lines.append(f"  {index}: {category_name}")

    yaml_file = yolo_dir / "data.yaml"
    yaml_file.write_text(
        "\n".join(yaml_lines) + "\n",
        encoding="utf-8",
    )

    ##生成训练集检查图
    draw_label_previews(
        train_output_dir,
        train_label_dir,
        yolo_dir / "previews" / "train",
        train_categories,
    )

    ##生成验证集检查图
    draw_label_previews(
        val_output_dir,
        val_label_dir,
        yolo_dir / "previews" / "val",
        val_categories,
    )

    ##显示最终结果
    print("\n数据处理完成，全部46类保留")
    print("训练标签：", train_label_dir)
    print("验证标签：", val_label_dir)
    print("YOLO配置：", yaml_file)
    print("测试图片尚无公开标注，本次不生成测试标签")

if __name__ == "__main__":
    datapro()


