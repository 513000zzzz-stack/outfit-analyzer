import json
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO


PROJECT_DIR = Path(r"D:\考核2\outfit-analyzer")
#完整服饰类别，用于整套配色；46类检测结果仍然全部保留
GARMENT_IDS = set(range(13))
NEUTRAL_NAMES = {"黑色", "白色", "灰色"}

def create_output_dir(base_dir):
    base_dir=Path(base_dir)
    if not base_dir.exists():
        base_dir.mkdir(parents=True,exist_ok=False)
        return base_dir
    run_number=2
    while True:
        output_dir=base_dir.parent/f"{base_dir.name}_{run_number}"
        try :
            output_dir.mkdir()
        except FileExistsError:
            # 这个编号已经存在，继续检查下一个编号
            run_number += 1
        else:
            # 目录创建成功，返回本次保存位置
            return output_dir
def inner_box(bbox, width, height):
    ##限制坐标，并向内收缩边缘的5%
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width, int(np.floor(x1))))
    y1 = max(0, min(height, int(np.floor(y1))))
    x2 = max(0, min(width, int(np.ceil(x2))))
    y2 = max(0, min(height, int(np.ceil(y2))))
    dx, dy = int(max(0, x2 - x1) * 0.05), int(max(0, y2 - y1) * 0.05)
    return [x1 + dx, y1 + dy, x2 - dx, y2 - dy]


def sample_pixels(pixels):
    ##控制颜色计算量，固定种子便于复现
    pixels = pixels.reshape(-1, 3)
    if len(pixels) > 12000:
        generator = np.random.default_rng(42)
        pixels = pixels[generator.choice(len(pixels), 12000, replace=False)]
    return pixels


def color_distribution(pixels):
    ##统计基础颜色；使用全部颜色组，避免只取三个聚类中心漏掉彩色点缀
    if pixels.size == 0:
        return [], np.empty((0, 3), dtype=np.uint8)
    pixels = sample_pixels(pixels)
    hsv = cv2.cvtColor(pixels.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)[0]
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    names = np.select(
        [(h < 10) | (h >= 170), h < 25, h < 35, h < 85,
         h < 100, h < 130, h < 155],
        ["红色", "橙色", "黄色", "绿色", "青色", "蓝色", "紫色"],
        default="粉色",
    ).astype(object)
    names[(h >= 10) & (h < 25) & (v < 190)] = "棕色"
    names[(h >= 10) & (h < 40) & (s < 100) & (v >= 160)] = "米色"
    names[((h < 10) | (h >= 155)) & (s < 160) & (v >= 170)] = "粉色"
    names[(h >= 100) & (h < 130) & (v < 110)] = "藏蓝色"
    names[s < 45] = "灰色"
    names[(s < 45) & (v >= 220)] = "白色"
    names[v < 55] = "黑色"

    ##每组选择接近Lab均值的实际像素作为代表色
    lab = cv2.cvtColor(pixels.reshape(1, -1, 3), cv2.COLOR_BGR2LAB)[0].astype(np.float32)
    palette = []
    for name in np.unique(names):
        indices = np.flatnonzero(names == name)
        group = lab[indices]
        nearest = int(np.argmin(np.sum((group - group.mean(axis=0)) ** 2, axis=1)))
        pixel_index = int(indices[nearest])
        rgb = [int(value) for value in pixels[pixel_index, ::-1]]
        palette.append({
            "name": str(name), "rgb": rgb,
            "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
            "ratio": float(len(indices) / len(pixels)),
            "hue_degrees": float(hsv[pixel_index, 0]) * 2,
        })
    return sorted(palette, key=lambda color: color["ratio"], reverse=True), hsv


def analyze_palette(palette, hsv):
    ##根据颜色比例、色相距离和明暗分布生成可解释的配色结论
    if not palette:
        return {"available": False, "description": "未检测到可分析的主要服饰，不生成整套配色结论。"}
    neutral_ratio = sum(c["ratio"] for c in palette if c["name"] in NEUTRAL_NAMES)
    chromatic = [c for c in palette if c["name"] not in NEUTRAL_NAMES and c["ratio"] >= 0.03]
    main = palette[0]
    dark_ratio = float(np.mean(hsv[:, 2] < 85))
    light_ratio = float(np.mean(hsv[:, 2] >= 180))
    relationships = []
    for left, right in combinations(chromatic, 2):
        delta = abs(left["hue_degrees"] - right["hue_degrees"])
        delta = min(delta, 360 - delta)
        relation = "同色系" if delta < 20 else "邻近色" if delta <= 60 else "近互补色" if delta >= 150 else "色相对比"
        relationships.append({
            "colors": [left["name"], right["name"]],
            "hue_difference": round(delta, 1), "relation": relation,
        })

    ##判定配色结构
    if not chromatic:
        scheme = "中性色配色"
    elif len(chromatic) == 1:
        scheme = "中性色搭配单一彩色" if neutral_ratio >= 0.5 else "单一彩色为主"
    elif len(chromatic) >= 4:
        scheme = "多色配色"
    elif any(pair["relation"] == "近互补色" for pair in relationships):
        scheme = "含近互补色对比的配色"
    elif all(pair["relation"] in {"同色系", "邻近色"} for pair in relationships):
        scheme = "同色系或邻近色配色"
    else:
        scheme = "含色相对比的配色"

    ##计算彩色部分的冷暖倾向；黑白灰不参与色相冷暖判断
    warm = cool = middle = 0.0
    for color in palette:
        if color["name"] in NEUTRAL_NAMES:
            continue
        hue = color["hue_degrees"]
        if hue < 75 or hue >= 330:
            warm += color["ratio"]
        elif 90 <= hue < 280:
            cool += color["ratio"]
        else:
            middle += color["ratio"]
    if warm + cool + middle < 0.05:
        temperature = "彩色区域较少，冷暖倾向不明显"
    elif warm > cool * 1.3 and warm > middle:
        temperature = "彩色部分偏暖"
    elif cool > warm * 1.3 and cool > middle:
        temperature = "彩色部分偏冷"
    else:
        temperature = "彩色部分冷暖混合或倾向不明显"

    contrast = "明暗对比明显" if dark_ratio >= 0.15 and light_ratio >= 0.15 else "以暗部为主" if dark_ratio >= 0.5 else "以亮部为主" if light_ratio >= 0.5 else "以中间明度为主"
    suggestions = []
    if len(chromatic) >= 4:
        suggestions.append("若希望视觉更简洁，可减少彩色种类，保留一种彩色作为重点。")
    elif neutral_ratio >= 0.7:
        suggestions.append("若希望增加变化，可使用小面积彩色配饰；当前配色也可保留中性色主导的特点。")
    if any(pair["relation"] == "近互补色" for pair in relationships):
        suggestions.append("若希望减弱色相对比，可降低其中一种对比色的面积或饱和度。")
    if not suggestions:
        suggestions.append("可结合穿着场景决定是否保留当前对比；颜色统计本身不能判定搭配好坏。")

    accents = [c for c in chromatic if c["ratio"] <= 0.2 and c["name"] != main["name"]]
    return {
        "available": True, "dominant_color": main, "palette": palette,
        "neutral_ratio": neutral_ratio, "scheme": scheme,
        "temperature": temperature, "contrast": contrast,
        "dark_ratio": dark_ratio, "light_ratio": light_ratio,
        "accent_candidates": accents, "relationships": relationships,
        "suggestions": suggestions,
        "description": f"分析区域以{main['name']}为主，约占{main['ratio']:.1%}；中性色合计{neutral_ratio:.1%}。判定为{scheme}，{temperature}，{contrast}。",
        "rules": {
            "significant_chromatic_min_ratio": 0.03,
            "similar_hue_max_degrees": 20,
            "analogous_hue_max_degrees": 60,
            "near_complementary_min_degrees": 150,
            "dark_value_below": 85, "light_value_at_least": 180,
            "contrast_min_dark_and_light_ratio": 0.15,
        },
    }


def save_palette(palette, path):
    ##色块等宽展示，比例在文字中标出
    colors = palette[:5]
    if not colors:
        return
    image = Image.new("RGB", (160 * len(colors), 110), "white")
    drawing = ImageDraw.Draw(image)
    for index, color in enumerate(colors):
        x = index * 160
        drawing.rectangle((x, 0, x + 159, 79), fill=tuple(color["rgb"]))
        drawing.text((x + 5, 85), f"{color['hex']} {color['ratio']:.1%}", fill="black")
    image.save(path)


def build_text_report(report):
    ##输出能直接阅读的色彩分析，而不只保存数字
    lines = ["服饰色彩与配色分析报告", f"原图：{report['image']}", "", "一、主要服饰候选"]
    garments = [item for item in report["objects"] if item["class_id"] in GARMENT_IDS]
    if not garments:
        lines.append("没有检测到主要服饰候选。")
    for item in garments:
        description = "、".join(f"{c['name']} {c['ratio']:.1%}" for c in item["colors"][:5])
        lines.append(f"目标{item['id']} {item['class_name']}（检测置信度{item['confidence']:.3f}）：{description or '没有有效区域'}")
    analysis = report["color_analysis"]
    lines.extend(["", "二、整体色彩分析", analysis["description"]])
    if analysis["available"]:
        lines.append("主要颜色：" + "、".join(f"{c['name']} {c['hex']} {c['ratio']:.1%}" for c in analysis["palette"][:5]))
        lines.append("点缀色候选：" + ("、".join(c["name"] for c in analysis["accent_candidates"]) or "没有达到规则阈值的候选"))
        lines.append(f"暗部占比{analysis['dark_ratio']:.1%}；亮部占比{analysis['light_ratio']:.1%}。")
        for pair in analysis["relationships"]:
            lines.append(f"{'与'.join(pair['colors'])}：色相差{pair['hue_difference']}°，按规则属于{pair['relation']}。")
        lines.extend(["", "三、可选配色建议", *analysis["suggestions"]])
    lines.extend(["", "四、分析依据与局限", *report["limitations"]])
    return "\n".join(lines)


def predicted_image(image_file, output_dir=None, device=0):
    ##检查输入并加载最佳模型
    image_file = Path(image_file)
    weight_file = PROJECT_DIR / "runs" / "detect" / "fashion_yolo26n" / "weights" / "best.pt"
    if not image_file.is_file():
        raise FileNotFoundError(f"找不到图片：{image_file}")
    if not weight_file.is_file():
        raise FileNotFoundError(f"找不到模型：{weight_file}")
    if output_dir is None:
        base_dir = PROJECT_DIR / "runs" / "color_analysis" / image_file.stem
    else:
        base_dir = Path(output_dir)
    output_dir = create_output_dir(base_dir)
    print(f"本次结果目录：{output_dir}")
    model = YOLO(str(weight_file))
    result = model.predict(source=str(image_file), imgsz=960, conf=0.25, device=device, save=False, verbose=False)[0]
    original = result.orig_img
    height, width = original.shape[:2]
    output_dir.mkdir(parents=True, exist_ok=True)
    result.save(filename=str(output_dir / "detection.jpg"))

    ##保留46类目标的局部颜色；主要服饰区域另做并集，防止重叠像素重复计数
    objects = []
    garment_mask = np.zeros((height, width), dtype=bool)
    overlap_found = False
    for index, box in enumerate(result.boxes, start=1):
        class_id = int(box.cls[0].item())
        raw_box = box.xyxy[0].cpu().numpy()
        bbox = inner_box(raw_box, width, height)
        x1, y1, x2, y2 = bbox
        region = original[y1:y2, x1:x2]
        palette, _ = color_distribution(region)
        item = {
            "id": index, "class_id": class_id, "class_name": result.names[class_id],
            "confidence": float(box.conf[0].item()),
            "detected_bbox": [float(value) for value in raw_box],
            "analysis_bbox": bbox, "colors": palette,
        }
        objects.append(item)
        if region.size:
            Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB)).save(output_dir / f"{index}_region.jpg")
            save_palette(palette, output_dir / f"{index}_colors.png")
            if class_id in GARMENT_IDS:
                overlap_found = overlap_found or bool(garment_mask[y1:y2, x1:x2].any())
                garment_mask[y1:y2, x1:x2] = True

    ##对主要服饰区域整体统计，再生成配色关系、明暗与冷暖分析
    overall_palette, overall_hsv = color_distribution(original[garment_mask])
    analysis = analyze_palette(overall_palette, overall_hsv)
    limitations = [
        "结果基于YOLO服饰候选框，检测错误会影响后续分析。",
        "颜色比例是服饰候选框并集区域的采样像素占比，不是衣物真实表面积。",
        "没有执行像素级服饰分割；背景、皮肤、遮挡和光照可能影响结果。",
        "整体配色仅使用类别0至12的完整服饰候选；配饰和部件仍保留独立检测及颜色记录。",
        "颜色命名、冷暖、色相关系及建议属于明确阈值下的规则分析，不是专业审美评分。",
        "尚未按人物分组，当前主要面向单人穿搭照片。",
    ]
    if overlap_found:
        limitations.append("主要服饰候选框存在重叠，可能来自叠穿或类别误判；整体统计已按像素并集去重，但无法自动消除错误类别。")
    report = {
        "image": str(image_file.resolve()), "objects": objects,
        "analysis_region_pixels": int(garment_mask.sum()),
        "color_analysis": analysis, "limitations": limitations,
    }

    ##保存结构化记录、可读分析报告和整体色卡
    (output_dir / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    text = build_text_report(report)
    (output_dir / "analysis.txt").write_text(text, encoding="utf-8")
    save_palette(overall_palette, output_dir / "overall_palette.png")
    print(text)
    print(f"\n结果目录：{output_dir}")
    return report


if __name__ == "__main__":
    image_path = input("请输入照片的完整路径：").strip().strip('"')
    predicted_image(image_path)
