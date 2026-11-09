import base64
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
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
PROMPT = """请分析这张穿搭照片，用中文给出以下内容：
一、服饰清单：区分完整衣物、配饰和服装部件，不要将袖子等重复计为完整衣物。
二、逐件颜色：说明每件衣物的主要颜色、可见图案和位置。
三、整体配色：说明主导色、点缀色、中性色、冷暖和明暗对比。
四、配色关系：说明哪些可见颜色形成邻近、相似或明显对比的关系，并说明依据。
五、可选建议：依据可见信息提供两条具体、条件性的配色建议，不武断评价好坏。
六、不确定项：说明模糊、遮挡、光照及类别歧义。
仅依据图片，不虚构品牌、价格或真实材质，不编造精确的颜色面积百分比。
如有多人，分别描述；无法确认的内容明确写不确定。
"""


def analyze_outfit(image_file, output_dir=None, verbose=True):
    image_file = Path(image_file)
    base_dir = Path(output_dir) if output_dir else PROJECT_DIR / "runs" / "doubao" / image_file.stem
    output_dir = create_output_dir(base_dir)
    if verbose:
        print(f"本次结果目录：{output_dir}")
    ##读取项目密钥配置
    load_dotenv(PROJECT_DIR / ".env", override=False)
    api_key = os.getenv("ARK_API_KEY", "").strip()
    model_name = os.getenv("ARK_MODEL", "").strip()
    if not api_key:
        raise RuntimeError("请先在项目根目录的.env文件中配置ARK_API_KEY。")
    if not model_name:
        raise RuntimeError("请先在项目根目录的.env文件中配置ARK_MODEL。")

    ##检查照片并转换成可传输的Base64字符串
    image_file = Path(image_file)
    if not image_file.is_file():
        raise FileNotFoundError(f"找不到照片：{image_file}")
    mime_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    mime = mime_types.get(image_file.suffix.lower())
    if mime is None:
        raise ValueError("本模块接收JPG、JPEG、PNG或WebP照片。")
    encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")

    ##组织豆包官方接口要求的请求内容
    payload = {
        "model": model_name,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{encoded}",
                }},
            ],
        }],
        "max_tokens": 2200,
        "thinking": {"type": "disabled"},
    }
    request = Request(
        url="https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    ##直接发送HTTP请求，不使用第三方模型调用SDK
    if verbose:
        print("正在将照片发送给豆包分析……")
    started = perf_counter()
    try:
        with urlopen(request, timeout=120) as http_response:
            response = json.loads(http_response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {})
            if isinstance(detail, dict):
                message = f"{detail.get('code', '')} {detail.get('message', '')}".strip()
            else:
                message = str(detail)
        except (json.JSONDecodeError, AttributeError):
            message = "服务器未返回可解析的错误信息。"
        raise RuntimeError(f"豆包请求失败，HTTP {error.code}：{message}") from None
    except URLError as error:
        raise RuntimeError(f"无法连接豆包接口：{error.reason}") from None
    elapsed = perf_counter() - started

    ##取得回答并检查是否有正文
    choices = response.get("choices", [])
    if not choices:
        raise RuntimeError("接口没有返回可读取的回答。")
    choice = choices[0]
    answer = choice.get("message", {}).get("content")
    if not answer:
        raise RuntimeError("豆包没有返回分析正文，请检查模型响应或账号权限。")
    finish_reason = choice.get("finish_reason")

    ##保存报告，以及后续方案对比需要的耗时和用量
    (output_dir / "analysis.txt").write_text(answer, encoding="utf-8")
    record = {
        "image": str(image_file.resolve()),
        "provider": "火山方舟", "requested_model": model_name,
        "returned_model": response.get("model"), "response_id": response.get("id"),
        "request_seconds": round(elapsed, 3),
        "finish_reason": finish_reason,
        "usage": response.get("usage"),
        "prompt": PROMPT, "answer": answer,
    }
    (output_dir / "analysis.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if verbose:
        print("\n" + answer)
        if finish_reason == "length":
            print("\n回答达到长度上限，分析可能不完整。")
        print(f"\n接口耗时：{elapsed:.2f}秒")
        print(f"结果目录：{output_dir}")
    return record


if __name__ == "__main__":
    image_path = input("请输入原始穿搭照片的完整路径：").strip().strip('"')
    analyze_outfit(image_path)
