# 穿搭分析系统（Outfit Analyzer）

一个基于 FastAPI 和 SQLAlchemy 构建的穿搭图片分析系统，支持用户注册登录、双方案并排分析、个人历史、备注与删除，可在 Linux 服务器上用 Docker Compose 一键部署。

## 1-1 项目概述

这是一个把「同一张穿搭照片交给两套模型分别分析」的过程做成网页应用的后端服务。用户上传一张照片后，系统先用 YOLO 训练权重检测服饰位置并统计颜色，再把同一张图交给豆包多模态大模型生成穿搭描述与建议，最终在网页左右两栏并排展示两种结果。

YOLO 推理和外部模型调用都比较慢，因此分析任务不占用请求线程：后端先把任务写入 PostgreSQL 并投递到 Redis 队列，接口立即返回任务编号，由独立的 Worker 进程在后台完成 YOLO 与豆包两条分析链路。前端拿任务编号轮询进度，先完成的一路可以先看到。整个过程使用 JWT 区分账号，历史记录、备注和结果附件都只能由本人访问。

系统面向课程第三阶段考核，重点不在模型精度，而在于把「Web 服务 + 数据库 + 队列 + 鉴权 + 容器化部署」这几层完整串起来并能讲清楚。

## 1-2 技术栈

- **后端框架**：FastAPI（路由、参数校验、依赖注入、OpenAPI 文档）
- **数据校验**：Pydantic v2
- **数据库**：PostgreSQL 16
- **ORM**：SQLAlchemy 2.0（同步 Session + psycopg3 驱动）
- **消息队列**：Redis 7 + RQ（Python 原生任务队列）
- **身份认证**：PyJWT（HS256）+ 加盐 PBKDF2-SHA256 口令摘要
- **网页**：Streamlit（登录、上传、进度轮询、并排结果、历史）
- **模型**：Ultralytics YOLO（自训练服饰检测权重）、火山方舟豆包 Seed 2.0 Lite（HTTP 接口）
- **图像处理**：OpenCV（BGR/HSV/Lab 色彩空间）、NumPy（区域采样与比例统计）、Pillow（裁剪、色卡、格式转换）
- **部署**：Dockerfile 多阶段构建、Docker Compose、nginx 反向代理

## 1-3 项目结构

```text
outfit-analyzer/
├── api.py                          # FastAPI 启动入口（uvicorn api:app）
├── ui.py                           # Streamlit 启动入口（streamlit run ui.py）
├── jobs.py                         # RQ Worker 任务入口：process_analysis
├── database.py                     # 兼容导入：对外暴露 Analysis / User / session
├── schemas.py                      # 兼容导入：对外暴露响应模型
│
├── outfit_api/                     # 后端应用
│   ├── app.py                      # 创建应用、注册中间件与路由、启动时建表
│   ├── config.py                   # 数据库引擎、会话、存储目录、Redis 地址
│   ├── auth.py                     # 口令哈希、JWT 签发与解析
│   ├── models.py                   # 用户表与分析记录表
│   ├── schemas.py                  # 统一响应结构、请求与响应模型
│   ├── dependencies.py             # 数据库会话、当前用户、表单来源校验
│   ├── middleware.py               # 请求日志中间件（方法、路径、耗时、用户、IP）
│   ├── logging_config.py           # API 与 Worker 共用的日志配置
│   ├── common/responses.py         # 统一响应与异常处理
│   ├── routers/
│   │   ├── health.py               # GET /api/health
│   │   ├── accounts.py             # /api/user/register、/login、/info
│   │   ├── browser_auth.py         # /browser-auth/* 浏览器表单登录与退出
│   │   └── analyses.py             # /api/analysis/* 上传、列表、详情、备注、删除、附件
│   ├── services/                   # 业务逻辑：账户、图片校验、入队、历史
│   └── crud/                       # 数据访问：按用户名/编号查询、分页、条件更新
│
├── outfit_ui/                      # 网页
│   ├── app.py                      # 页面装配
│   ├── client.py                   # 调用 API、解包统一响应、统一错误提示
│   ├── state.py / styles.py        # 会话状态、样式与时间格式化
│   └── views/                      # account / analysis / history / results
│
├── inference/
│   ├── model_test.py               # YOLO 检测 + 颜色统计 + 规则配色报告
│   └── ai_analysis.py              # 豆包多模态调用与结果落盘
│
├── training/                       # 数据准备、训练、续训脚本与训练日志
├── requirements/                   # 按服务拆分的依赖清单
├── compose.yaml / Dockerfile / deploy/nginx.conf
├── tests/                          # pytest 用例与 test_main.http
└── docs/                           # 本设计说明、接口规范、验收清单
```

**分层约定**：路由层只声明 URL、方法、请求/响应模型和身份依赖；service 层负责业务规则与事务提交；crud 层只做查询和条件更新；model 层定义表结构；schema 层定义接口传输的数据。`get_db()` 为每个请求提供一个数据库会话，认证依赖与业务逻辑共享同一会话，请求结束后自动关闭。

## 1-4 功能模块

### 1. 用户管理模块

- 用户注册（用户名唯一、口令加盐摘要存储）
- 用户登录并签发 JWT
- 获取当前登录账号信息
- 浏览器表单登录：成功后写入 HttpOnly Cookie 并跳回首页
- 刷新页面时用 Cookie 恢复登录会话，退出时清除 Cookie

### 2. 分析模块

- 上传图片（JPEG / PNG / WebP，最大 10 MB、1600 万像素）
- 校正 EXIF 方向后统一转存为 JPEG，两套方案共用这一份输入
- 创建任务记录并入队，接口立即返回任务编号
- 按任务编号查询状态与双方案结果
- 修改备注、删除已结束的记录
- 读取原图、检测图、整体色卡和 YOLO 文字报告

### 3. 双方案分析模块

- YOLO：检测服饰类别与位置，按检测框并集做整体颜色统计，生成主导色、中性色比例、冷暖倾向、明暗对比和色相关系
- 豆包：把整张图转 Base64 交给多模态模型，生成服饰清单、逐件颜色、整体配色与搭配建议
- 结果对比：两栏并排展示；一路失败时另一路仍可查看，任务状态标记为 `partial`

### 4. 历史模块

- 按页码读取本人分析历史，返回列表、总数和是否还有下一页
- 记录按创建时间倒序，时间相同按任务编号倒序
- 其他账号访问同一记录统一返回 404，不泄露记录是否存在

### 5. 后台任务模块

- Redis 队列存放待执行任务，Worker 独立进程消费
- 原子认领：`queued` 记录直接认领；已超时（超过 11 分钟）的 `running` 记录会在任务重新投递时被重新认领，认领时写入 `started_at`，重复投递不会重复调用模型
- 任务超时 600 秒，失败时由回调把记录标记为 `failed` 或 `partial`
- API 启动时清理超时任务：`queued` 超过 30 分钟、`running` 超过 11 分钟或没有 `started_at` 的记录落为终态，避免永久停在「分析中」
- 任务日志以任务编号（即 RQ job id）关联，可同时 `grep` API 与 Worker 输出

## 1-5 数据库设计

### 主要数据表

1. **用户表 `users`**
   - `id`：主键，自增整数
   - `username`：唯一用户名，保存为小写，3–32 位字母、数字或下划线
   - `password_hash`：`盐值十六进制:PBKDF2 摘要`，PBKDF2-SHA256 迭代 60 万次
   - `bio`：个性签名，默认「这个人很懒，什么都没留下」
   - `avatar`：头像地址，未上传时为空字符串

2. **分析记录表 `analyses`**
   - `id`：主键，UUID 字符串（同时作为任务编号和 RQ job id）
   - `owner_id`：外键指向 `users.id`，与 `created_at` 组成复合索引
   - `filename`：上传文件名，仅用于展示
   - `created_at`：创建时间，带时区
   - `started_at`：Worker 认领时间，用于判断执行是否超时
   - `status`：`queued` / `running` / `completed` / `partial` / `failed`
   - `note`：个人备注，最长 1000 字符
   - `yolo`、`doubao`：两路结果，JSON 存储，未生成时为 `null`

### 表关系

`users.id` 与 `analyses.owner_id` 是一对多关系：一个用户可以有多条分析记录，一条记录只属于一个用户。删除记录时校验归属，其他用户读取或修改一律返回 404。

### 建表方式

API 进程启动时执行 `Base.metadata.create_all` 建表。`create_all` 不会修改已存在的表，因此新增字段时用一段幂等的 `ALTER TABLE ... ADD COLUMN` 补齐，新增索引用 `CREATE INDEX IF NOT EXISTS`（见 `app.py` 的 `ensure_schema`）。课程项目没有引入 Alembic，改动表结构时同步修改模型和这段补列逻辑即可。

### 文件存储

图片和中间产物保存在共享文件卷中，目录名为任务 UUID：

```text
/var/lib/outfit/{analysis_id}/
├── input.jpg                 # 校正方向后的上传图
├── yolo/
│   ├── detection.jpg         # 检测框可视化
│   ├── overall_palette.png   # 整体色卡
│   ├── analysis.txt          # 规则配色报告
│   ├── analysis.json         # 结构化结果
│   └── {n}_region.jpg ...    # 每个目标的局部裁剪与色卡
└── doubao/
    ├── analysis.txt          # 模型正文
    └── response.json         # 原始响应、耗时、Token 用量
```

API 与 Worker 挂载同一个卷，接口只按白名单提供 4 个固定文件名，避免路径穿越。

## 1-6 队列与缓存设计

### 为什么用队列

YOLO 推理在 CPU 上需要数秒到数十秒，豆包请求依赖外网延迟，两者都不适合放在 HTTP 请求里同步等待。提交接口只做「校验 → 落盘 → 写库 → 入队 → 返回编号」，其余交给 Worker，请求可以稳定地快速返回。

### 队列实现

- Redis 作为 broker，RQ 作为任务队列，队列名 `outfit`
- 投递时指定 `job_id = analysis_id`，任务编号与队列任务一一对应，方便查日志
- `job_timeout=600`，`stop_grace_period: 6m` 保证容器重启时正在执行的模型调用有机会结束
- 失败回调把仍处于 `queued` / `running` 的记录标记为终态；Worker 被强杀后任务重新投递时，超时的 `running` 记录会被重新认领，避免永久停在「分析中」

### 缓存说明

本项目的 Redis 只承担队列职责，不缓存业务数据。历史与详情每次从 PostgreSQL 读取，保证备注修改、删除和任务状态变化能立即反映到页面；数据量在演示规模下也远没有到需要缓存的量级。若后续出现读压力，可按用户维度定义 `history:{user_id}:{page}` 这类键，并在写入后失效。

## 1-7 日志与可观测性

- API 与 Worker 共用 `outfit_api/logging_config.py`，默认输出到容器标准输出，用 `docker compose logs api`、`docker compose logs worker` 查看
- `LOG_LEVEL` 调整级别，`LOG_FILE` 额外写文件；Compose 给各服务配置了 `json-file` 的 10 MB × 3 份轮转，长期运行不会撑满磁盘
- 请求中间件为每个请求记录一行：方法、路径、状态码、耗时、当前用户、来源 IP；`/api/health` 等探针路径不记录，避免淹没业务日志
- 注册与登录的成功、失败写审计行，只记用户名和结果，不记密码和令牌
- 分析任务日志用任务编号关联，同一条记录可以同时对照 API 与 Worker 的输出
- nginx 的访问日志用 `docker compose logs nginx` 查看

## 1-8 API 接口说明

### 服务状态

| 接口          | 方法 | 说明          |
| ------------- | ---- | ------------- |
| `/api/health` | GET  | 检查 API 进程 |

### 用户相关接口

| 接口                 | 方法 | 说明             |
| -------------------- | ---- | ---------------- |
| `/api/user/register` | POST | 注册并签发令牌   |
| `/api/user/login`    | POST | 登录并签发令牌   |
| `/api/user/info`     | GET  | 获取当前账号信息 |

### 浏览器会话接口

| 接口                     | 方法 | 说明                       |
| ------------------------ | ---- | -------------------------- |
| `/browser-auth/login`    | GET  | 打开登录表单页面           |
| `/browser-auth/login`    | POST | 校验账号，写 Cookie 并跳转 |
| `/browser-auth/register` | POST | 注册并保持登录             |
| `/browser-auth/renew`    | POST | 续存浏览器 Cookie          |
| `/browser-auth/logout`   | GET  | 打开退出确认页             |
| `/browser-auth/logout`   | POST | 清除 Cookie 并跳转首页     |

### 分析相关接口

| 接口                                      | 方法   | 说明                     |
| ----------------------------------------- | ------ | ------------------------ |
| `/api/analysis/create`                    | POST   | 上传图片并创建分析任务   |
| `/api/analysis/list`                      | GET    | 分页读取个人历史         |
| `/api/analysis/detail/{analysis_id}`      | GET    | 查询任务状态与双方案结果 |
| `/api/analysis/note/{analysis_id}`        | PUT    | 修改备注                 |
| `/api/analysis/delete/{analysis_id}`      | DELETE | 删除已结束的记录         |
| `/api/analysis/file/{analysis_id}/{name}` | GET    | 读取原图、检测图或报告   |

全部 JSON 接口返回统一结构，字段示例与请求参数见 [API 接口规范文档](API_DESIGN.md)。

## 1-9 认证机制

系统使用基于 JWT 的无状态认证，并用 Cookie 承载浏览器会话：

1. 注册或登录成功后，`POST /api/user/register`、`/api/user/login` 返回 `token`
2. 需要认证的接口在请求头中携带 `Authorization: Bearer <token>`
3. 令牌载荷包含 `sub`（用户编号）、`iat`、`exp`，使用 HS256 签名，`JWT_SECRET` 至少 32 字节
4. 普通 API 客户端令牌有效期为 2 小时；浏览器登录单独签发有效期 1000 天的令牌，写入 `outfit_token` Cookie（`HttpOnly`、`SameSite=Lax`、`Path=/`）
5. 页面刷新时用 Cookie 中的令牌调用 `/api/user/info` 恢复会话，并在再次访问时续存 Cookie（不延长令牌本身的到期时间）
6. JWT 只回答「这个请求是谁」，**记录归属仍要单独校验**：查询详情、附件、备注、删除时都按 `owner_id` 过滤，他人记录统一返回 404

浏览器表单接口会校验 `Origin` 请求头与本站一致，跨站提交返回 403，降低 CSRF 风险。

## 1-10 错误处理

所有 `/api/` 下的接口使用同一套错误结构，HTTP 状态码与 `code` 保持一致：

```json
{
  "code": 404,
  "message": "找不到这条分析记录",
  "data": null
}
```

参数校验失败时 `data` 给出字段问题列表：

```json
{
  "code": 422,
  "message": "请求参数不符合要求",
  "data": [
    {
      "loc": ["query", "pageSize"],
      "msg": "Input should be less than or equal to 100",
      "type": "less_than_equal"
    }
  ]
}
```

| 状态码 | 含义                                     |
| ------ | ---------------------------------------- |
| 401    | 缺少、过期或无效的 JWT                   |
| 403    | 浏览器表单来源不符                       |
| 404    | 记录或文件不存在，或不属于当前账号       |
| 409    | 用户名已被使用，或任务仍在执行、不能删除 |
| 413    | 图片字节数或像素数超过限制               |
| 415    | 图片格式不支持或无法解码                 |
| 422    | 请求字段缺失或不符合约束                 |
| 500    | 数据库操作异常，详细堆栈只留在服务日志里 |

## 1-11 开发规范

- 路由只做参数声明和调用，业务规则集中在 `services/`，查询集中在 `crud/`
- 接口输入输出一律用 Pydantic 模型声明，响应模型同时驱动 OpenAPI 文档
- 所有 `/api/` 接口返回 `code / message / data`，浏览器会话接口保持 HTML 与重定向语义
- 密码只保存 PBKDF2 摘要，日志与响应中不出现密码、令牌和真实密钥
- 上传文件先校验再落盘，失败时清理任务目录；文件名只用于展示，磁盘路径由 UUID 决定
- 配置项全部走环境变量，`.env` 不入库，仓库只提供 `.env.example`
- 修改行为要同步更新 `tests/` 与 `docs/`，保证文档描述的接口与实现一致

## 1-12 性能与部署

- **镜像分层**：Dockerfile 用多阶段构建，API / Worker / UI 共用同一基础层，各自只装需要的依赖
- **CPU 推理**：Worker 从 PyTorch CPU 源安装轮子，避免在服务器上下载 CUDA 工具包
- **并发模型**：API 用 uvicorn 单进程多协程处理请求，耗时操作全部移出请求线程；需要扩容时直接增加 Worker 副本
- **数据库**：`pool_pre_ping=True` 避免连接被中间层断开后报错；`owner_id` 建索引，历史查询按用户过滤后分页
- **连接复用**：数据库引擎按连接串缓存，避免每次请求重建
- **日志轮转**：容器日志按 10 MB × 3 份轮转，长期运行不会撑满磁盘
- **持久化**：数据库、Redis 和分析文件各自使用数据卷，`docker compose restart` 后历史与结果仍可读取
- **入口收敛**：浏览器只访问 nginx 的 8080；nginx 把 `/api/` 和 `/browser-auth/` 转给 FastAPI，其余走 Streamlit
