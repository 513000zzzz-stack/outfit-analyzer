import json
from collections import Counter
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]

ANNOTATION_PATH = (
    PROJECT_DIR
    / "data"
    / "raw"
    / "instances_attributes_val2020.json"
)

# 项目类别与数据集原始类别编号的对应关系。
CATEGORY_GROUPS = {
    "upper": [0, 1, 2, 3, 4, 5, 9, 12],
    "lower": [6, 7],
    "skirt": [8],
    "dress": [10],
}


def main():
    if not ANNOTATION_PATH.exists():
        raise FileNotFoundError(
            f"找不到标注文件，请先下载：{ANNOTATION_PATH}"
        )

    text = ANNOTATION_PATH.read_text(encoding="utf-8")
    data = json.loads(text)

    print("图片数量：", len(data["images"]))
    print("标注数量：", len(data["annotations"]))

    print("\n原始类别：")

    for category in data["categories"]:
        print(category["id"], category["name"])

    # 统计每个原始类别的标注数量。
    source_counts = Counter()

    for annotation in data["annotations"]:
        source_id = annotation["category_id"]
        source_counts[source_id] += 1

    print("\n项目四大类的标注数量：")

    selected_total = 0

    for target_name, source_ids in CATEGORY_GROUPS.items():
        count = 0

        for source_id in source_ids:
            count += source_counts[source_id]

        selected_total += count
        print(f"{target_name}: {count}")

    excluded_total = len(data["annotations"]) - selected_total

    print("\n纳入统计的标注数量：", selected_total)
    print("排除的标注数量：", excluded_total)


if __name__ == "__main__":
    main()