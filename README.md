## 第三阶段 · 穿搭对比应用

上传同一张照片，比较 YOLO 的服饰检测和颜色统计与豆包的穿搭分析，结果可保存到个人历史。

- [项目设计说明](docs/PROJECT_DESIGN.md)
- [API 接口规范](docs/API_DESIGN.md)
- [考核验收与录屏清单](docs/ASSESSMENT.md)

服务入口为 `api.py` 和 `ui.py`。后端代码在 `outfit_api/`，页面代码在 `outfit_ui/`。在 Linux 服务器准备 `.env` 与 `models/best.pt` 后，用 `docker compose up -d --build` 启动整套服务。

---

# Outfit Analyzer 第一阶段
一.项目简介
1，处理数据集，使之符合YOLO的训练数据集的处理要求
    数据集来源：[cvdfoundation/fashionpedia](https://github.com/cvdfoundation/fashionpedia#annotation-format)
    主要使用数据集中关于服饰类别和服饰位置标注的内容

2，使用YOLO26n,加载预训练权重，训练YOLO,最多训练150次，40次权重数据没变化后即停止
    由于时间限制和条件限制，只训练了28次，最好轮次为第28轮（mAP50 0.483，mAP50-95 0.370，precision 0.637，recall 0.456），权重保存在 `runs/detect/fashion_yolo26n/weights/best.pt`。

3，颜色分析
根据 YOLO 检测框，从原始照片中取得目标区域，再进行颜色分析。
使用 NumPy 完成区域裁剪、像素采样、数组筛选和比例统计；使用 OpenCV 将 BGR 像素转换为 HSV，根据色相、饱和度和明亮程度划分基础颜色，再通过 Lab 空间选择各颜色组的代表像素。
使用 Pillow 保存目标区域图片、绘制颜色色卡。
在局部颜色统计基础上，对完整服饰候选区域取像素并集，避免重叠框和服装部件被重复累计，再分析主导色、中性色比例、点缀色候选、冷暖倾向、明暗对比及色相关系，生成规则配色报告。
当前使用检测框近似衣物区域，尚未执行像素级服饰分割，因此背景、皮肤、遮挡和光照仍可能干扰结果。

4，大模型处理
使用豆包 Seed 2.0 Lite，通过 Python 自带的 urllib 直接调用火山方舟 HTTP 接口。
将本地照片转换为 Base64，结合图片类型、模型名称和提示词组织 JSON 请求。API Key 和模型配置通过 `.env` 文件读取。
提示词要求模型分析服饰清单、逐件颜色、图案、整体配色和颜色关系，提供基于图片的可选建议，并明确说明遮挡、模糊和无法确认的内容。
程序保存模型回答，同时记录接口请求耗时、模型标识、Token 用量和结束原因，便于后续复查和方案比较。



5，并排展示与方案对比
![[0a4f8205a3b58e70eec99fbbb9422d08.jpg|380]]![0a4f8205a3b58e70eec99fbbb9422d08.jpg](data/yolo/images/test/0a4f8205a3b58e70eec99fbbb9422d08.jpg)

+ YOLO
![detection.jpg](runs/color_analysis/0a4f8205a3b58e70eec99fbbb9422d08/detection.jpg)
[analysis.txt](runs/color_analysis/0a4f8205a3b58e70eec99fbbb9422d08/analysis.txt)
![overall_palette.png](runs/color_analysis/0a4f8205a3b58e70eec99fbbb9422d08/overall_palette.png)

+ 大模型
[analysis.txt](runs/doubao/0a4f8205a3b58e70eec99fbbb9422d08/analysis.txt)


+ 对比
    类别与位置：主题服饰识别大体一致，YOLO没识别出面纱
    颜色与配色：YOLO将肤色混在其中，怀疑是框选区域太大，将皮肤框选在其中，而将肤色识别为服饰
    解释与建议：YOLO的解释与功能功能是通过人为编写的python，由编写人规定的规则分析匹配的，单板，不贴切
    使用体验与场景：YOLO在目标定位，框选上做的还可以，如果有足够好（框选准确，标签准确）的足量的数据集的训练，再加上足够轮次的训练，表现接近大模型表现，适合位置输出，识别类别，和追踪任务
                  大模型可以直接给出图文语义描述和建议，适合交叉式观察，分析


# 第二阶段

这个项目把第二阶段的两套穿搭分析放进同一个网页。登录后上传一张照片，系统排队处理，并排展示 YOLO 的检测图、颜色统计与豆包的穿搭描述。可以从个人历史中再次打开分析、修改备注或删除已结束的记录。

1. 用 Streamlit 做页面，用 FastAPI 接收请求

Streamlit 负责登录、图片上传、进度显示和结果展示。用户点「提交双方案分析」后，页面把图片交给 FastAPI。后端检查登录状态和上传文件，保存图片，创建分析记录，再返回任务编号。网页根据这个编号查询进度和结果。

2. 用 Redis 队列安排后台分析

YOLO 推理和豆包请求都需要时间，所以后端先把任务交给 Redis 队列，由 Worker 取出任务并执行。两种方案读取同一张上传图，各自保存结果。假如豆包请求失败，网页仍然可以显示已经生成的 YOLO 检测图和色卡。原来的模型和颜色分析规则继续沿用，主要改动是让后台可以给每次分析指定独立的输出目录。

3. 用 PostgreSQL 保存历史，用 JWT 区分账号

项目通过 SQLAlchemy 操作 PostgreSQL。上传图片时新增一条记录，打开历史时查询记录，修改备注时更新记录，也可以删除自己已结束的任务。登录成功后，FastAPI 签发 JWT。之后打开记录或查看检测图时，后端会核对这条记录属于哪个账号。

4. 用 Docker Compose 组织部署

项目通过 Dockerfile 声明各服务的依赖和启动方式，用 Docker Compose 管理网页、API、Worker、PostgreSQL、Redis 和 nginx。nginx 提供网页访问入口，数据库和分析文件放在数据卷中。训练权重通过挂载提供给 Worker，豆包密钥等配置由服务器上的 .env 提供。

三、同一张图片的结果对比

