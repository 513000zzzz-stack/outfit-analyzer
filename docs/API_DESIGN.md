# API 接口规范

## 概述

本文档描述穿搭分析系统的全部接口，包括服务状态、用户管理、浏览器会话、穿搭分析四个模块。

系统把同一张穿搭照片交给两套方案分析：YOLO 负责服饰检测与颜色统计，豆包多模态大模型负责穿搭描述与建议。上传接口只创建任务并立即返回任务编号，分析在后台队列中执行，客户端用任务编号轮询进度。

接口实现、分层结构和部署方式见 [项目后端设计说明](PROJECT_DESIGN.md)。

## 基础 URL

```
http://localhost:8000
```

直接访问 FastAPI 容器时使用上面的地址。经过服务器上的 nginx 入口时，把地址换成 `http://<服务器地址>:8080`，`/api/` 与 `/browser-auth/` 会被转发到 FastAPI，其余路径转发给网页。

## 认证方式

除服务状态、注册、登录和浏览器会话接口外，其余接口都需要认证，认证通过在请求头中添加 `Authorization` 字段实现：

```
Authorization: Bearer <token>
```

`token` 来自注册或登录接口返回的 `data.token`。令牌载荷包含用户编号、签发时间和过期时间，使用 HS256 签名，普通接口有效期为 2 小时。

令牌只回答「请求来自哪个账号」。查询、修改或删除某条分析记录时，后端还会核对这条记录是否属于该账号，不属于时统一返回 `404`。

## 响应格式

除附件下载和浏览器会话接口外，所有接口返回 JSON，统一结构如下：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

| 字段    | 类型   | 说明                                       |
| ------- | ------ | ------------------------------------------ |
| code    | int    | 业务状态码，与 HTTP 状态码保持一致          |
| message | string | 结果说明，成功时为 `success` 或具体提示文字 |
| data    | any    | 业务数据；没有返回内容时为 `null`           |

出错时沿用同一结构，`data` 通常为 `null`；请求参数校验失败时，`data` 为字段问题列表：

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

时间字段统一使用 ISO 8601 字符串，带时区偏移，例如 `2026-11-09T02:00:00+00:00`。

## 接口详情

### 服务状态模块

#### 1. 健康检查

- **接口地址**: `GET /api/health`
- **请求参数**: 无
- **响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "status": "ok"
  }
}
```

该接口只说明 API 进程能响应，不代表 Worker、模型或豆包接口可用。Docker Compose 用它作为 API 容器的健康检查。

### 用户模块

#### 1. 用户注册

- **接口地址**: `POST /api/user/register`
- **请求参数**:

| 参数名   | 类型   | 必填 | 说明                                          |
| -------- | ------ | ---- | --------------------------------------------- |
| username | string | 是   | 3–32 位英文字母、数字或下划线，保存时转为小写 |
| password | string | 是   | 8–128 个字符                                  |

- **请求示例**:

```json
{
  "username": "outfit_demo",
  "password": "example-password"
}
```

- **响应示例**:

```json
{
  "code": 200,
  "message": "注册成功",
  "data": {
    "token": "<JWT>",
    "userInfo": {
      "id": 1,
      "username": "outfit_demo",
      "bio": "这个人很懒，什么都没留下",
      "avatar": ""
    }
  }
}
```

注册成功即签发令牌，客户端不必再调用一次登录。用户名重复返回 `409`，格式不符合要求返回 `422`。

#### 2. 用户登录

- **接口地址**: `POST /api/user/login`
- **请求参数**: 同注册
- **请求示例**:

```json
{
  "username": "outfit_demo",
  "password": "example-password"
}
```

- **响应示例**:

```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "<JWT>",
    "userInfo": {
      "id": 1,
      "username": "outfit_demo",
      "bio": "这个人很懒，什么都没留下",
      "avatar": ""
    }
  }
}
```

账号不存在或密码错误均返回 `401`，`message` 分别为「该账号尚未注册，请先注册。」与「密码错误，请重新输入。」。

#### 3. 获取用户信息

- **接口地址**: `GET /api/user/info`
- **请求头**: 需要认证
- **请求参数**: 无
- **响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "username": "outfit_demo",
    "bio": "这个人很懒，什么都没留下",
    "avatar": ""
  }
}
```

网页刷新时用它验证 Cookie 中的令牌是否仍然有效，有效则恢复登录状态。

### 浏览器会话模块

这一组接口给网页的登录表单使用，返回 HTML 页面或 30x 重定向，不使用 JSON 结构。网页的登录框直接 `POST` 到这些地址，由 FastAPI 校验账号并把令牌写入 `outfit_token` Cookie。

| 接口                     | 方法 | 说明                                   |
| ------------------------ | ---- | -------------------------------------- |
| `/browser-auth/login`    | GET  | 返回登录表单 HTML                      |
| `/browser-auth/login`    | POST | 校验账号，写入 Cookie，`303` 跳转 `/`  |
| `/browser-auth/register` | POST | 注册并写入 Cookie，`303` 跳转 `/`      |
| `/browser-auth/renew`    | POST | 续存 Cookie，成功 `204`，无 Cookie `401` |
| `/browser-auth/logout`   | GET  | 返回退出确认页 HTML                    |
| `/browser-auth/logout`   | POST | 清除 Cookie，`303` 跳转 `/`            |

- **请求参数**: 表单类型 `application/x-www-form-urlencoded`，字段为 `username`、`password`
- **Cookie 属性**: `HttpOnly`、`SameSite=Lax`、`Path=/`，有效期与浏览器登录令牌一致
- **来源校验**: 后端比对 `Origin` 请求头与本站地址，不一致返回 `403`
- **响应示例**（登录成功时的重定向，`303`）:

```
Location: /
Set-Cookie: outfit_token=<JWT>; HttpOnly; Path=/; SameSite=lax; Max-Age=86400000
```

退出只清除当前浏览器的 Cookie，已被复制走的令牌仍按自身有效期失效。

### 分析模块

以下接口都需要认证。

#### 1. 创建分析任务

- **接口地址**: `POST /api/analysis/create`
- **请求类型**: `multipart/form-data`
- **请求参数**:

| 参数名 | 类型 | 必填 | 说明                                   |
| ------ | ---- | ---- | -------------------------------------- |
| image  | file | 是   | JPEG、PNG 或 WebP，最大 10 MB、1600 万像素 |

- **请求示例**:

```bash
curl -X POST "$API_BASE/api/analysis/create" \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@outfit.jpg"
```

- **成功响应**: HTTP `202`，返回任务快照

```json
{
  "code": 202,
  "message": "任务已创建",
  "data": {
    "id": "16f17fbc-51da-4e6f-8bf4-3d38c84a567e",
    "filename": "outfit.jpg",
    "created_at": "2026-11-09T02:00:00+00:00",
    "status": "queued",
    "note": "",
    "yolo": null,
    "doubao": null
  }
}
```

- **错误响应**: `413` 字节数或像素数超限；`415` 格式不支持或无法解码；`401` 未登录

上传后系统校正图片方向、统一存为 JPEG，然后写入 `queued` 记录并投递到 Redis 队列。请求返回时任务可能已经开始执行，状态以响应为准。队列不可用时记录直接标记为 `failed`，返回的 `data` 中两路结果是错误摘要。

#### 2. 获取分析历史

- **接口地址**: `GET /api/analysis/list`
- **请求参数**:

| 参数名   | 类型    | 必填 | 说明                               |
| -------- | ------- | ---- | ---------------------------------- |
| page     | integer | 否   | 页码，默认 1，从 1 开始             |
| pageSize | integer | 否   | 每页条数，默认 20，范围 1–100       |

- **请求示例**:

```
GET /api/analysis/list
GET /api/analysis/list?page=2&pageSize=20
```

- **响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "list": [
      {
        "id": "16f17fbc-51da-4e6f-8bf4-3d38c84a567e",
        "filename": "outfit.jpg",
        "created_at": "2026-11-09T02:00:00+00:00",
        "status": "completed",
        "note": "对比记录",
        "yolo": {
          "status": "ok",
          "seconds": 3.42,
          "data": {
            "objects": [],
            "color_analysis": {},
            "limitations": []
          }
        },
        "doubao": {
          "status": "ok",
          "seconds": 7.18,
          "data": {
            "answer": "画面中……",
            "request_seconds": 6.94,
            "usage": {"total_tokens": 1280},
            "returned_model": "doubao-seed-2-0-lite-260428",
            "finish_reason": "stop"
          }
        }
      }
    ],
    "total": 1,
    "hasMore": false
  }
}
```

列表只返回当前账号的记录，按创建时间倒序，时间相同时按任务编号倒序。`total` 只统计本人记录，`hasMore` 表示是否还有下一页；页码超过最后一页时返回空列表。

#### 3. 获取任务详情

- **接口地址**: `GET /api/analysis/detail/{analysis_id}`
- **路径参数**:

| 参数名      | 类型   | 必填 | 说明         |
| ----------- | ------ | ---- | ------------ |
| analysis_id | string | 是   | 分析任务编号 |

- **请求示例**:

```
GET /api/analysis/detail/16f17fbc-51da-4e6f-8bf4-3d38c84a567e
```

- **响应示例**: 结构与上一条列表中的单条记录相同

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "16f17fbc-51da-4e6f-8bf4-3d38c84a567e",
    "filename": "outfit.jpg",
    "created_at": "2026-11-09T02:00:00+00:00",
    "status": "partial",
    "note": "",
    "yolo": {
      "status": "ok",
      "seconds": 3.42,
      "data": {
        "objects": [
          {
            "id": 1,
            "class_id": 6,
            "class_name": "dress",
            "confidence": 0.91,
            "colors": [{"name": "白色", "hex": "#F2F0EA", "ratio": 0.62}]
          }
        ],
        "color_analysis": {"description": "以白色为主……", "palette": []},
        "limitations": ["结果基于YOLO服饰候选框，检测错误会影响后续分析。"]
      }
    },
    "doubao": {
      "status": "error",
      "seconds": 2.05,
      "error": "豆包 分析失败，请查看 Worker 日志和运行配置。"
    }
  }
}
```

任务状态依次可能是 `queued`、`running`，终态为 `completed`、`partial`、`failed`。分支字段 `yolo`、`doubao` 未生成时为 `null`；生成后包含 `status`（`ok` 或 `error`）、可选的耗时 `seconds`，成功时是 `data`，失败时是 `error`。一路失败时另一路仍可读。

YOLO 的 `data` 可能包含 `objects`（检测明细）、`color_analysis`（整体配色与主导色）、`limitations`（统计范围和局限）。豆包的 `data` 可能包含 `answer`（正文）、`request_seconds`、`usage`、`returned_model`、`finish_reason`。

#### 4. 修改备注

- **接口地址**: `PUT /api/analysis/note/{analysis_id}`
- **请求参数**:

| 参数名 | 类型   | 必填 | 说明                   |
| ------ | ------ | ---- | ---------------------- |
| note   | string | 是   | 备注内容，最多 1000 字符 |

- **请求示例**:

```json
{
  "note": "检测框含皮肤，颜色比例偏高"
}
```

- **响应示例**: 返回更新后的任务快照，`data` 结构与详情接口相同

```json
{
  "code": 200,
  "message": "备注已保存",
  "data": {
    "id": "16f17fbc-51da-4e6f-8bf4-3d38c84a567e",
    "filename": "outfit.jpg",
    "created_at": "2026-11-09T02:00:00+00:00",
    "status": "completed",
    "note": "检测框含皮肤，颜色比例偏高",
    "yolo": null,
    "doubao": null
  }
}
```

传空字符串可以清除备注。

#### 5. 删除分析记录

- **接口地址**: `DELETE /api/analysis/delete/{analysis_id}`
- **路径参数**: 同详情接口
- **请求示例**:

```
DELETE /api/analysis/delete/16f17fbc-51da-4e6f-8bf4-3d38c84a567e
```

- **响应示例**:

```json
{
  "code": 200,
  "message": "删除成功",
  "data": null
}
```

删除会同时清理该任务的分析文件。排队或运行中的任务返回 `409`「请等待分析结束后再删除」，其他账号的记录返回 `404`。

#### 6. 获取分析附件

- **接口地址**: `GET /api/analysis/file/{analysis_id}/{name}`
- **路径参数**:

| 参数名      | 类型   | 必填 | 说明                                                    |
| ----------- | ------ | ---- | ------------------------------------------------------- |
| analysis_id | string | 是   | 分析任务编号                                            |
| name        | string | 是   | `input.jpg`、`detection.jpg`、`overall_palette.png`、`analysis.txt` |

- **请求示例**:

```
GET /api/analysis/file/16f17fbc-51da-4e6f-8bf4-3d38c84a567e/detection.jpg
```

- **响应**: 直接返回二进制图片（`image/jpeg` 或 `image/png`）或 UTF-8 文本（`text/plain`）

`input.jpg` 是校正方向后的原图，`detection.jpg` 是检测框可视化，`overall_palette.png` 是整体色卡，`analysis.txt` 是 YOLO 的完整文字报告（已省略容器内部的原图路径）。文件名不在白名单、文件尚未生成、记录不属于当前账号时均返回 `404`。响应头带 `Cache-Control: private, no-store`，避免浏览器缓存他人的图片。

## 错误码

| 状态码 | 含义                                     |
| ------ | ---------------------------------------- |
| 200    | 请求成功                                 |
| 202    | 任务已受理，正在后台执行                 |
| 401    | 缺少、过期或无效的 JWT                   |
| 403    | 浏览器表单来源不符                       |
| 404    | 记录或文件不存在，或不属于当前账号       |
| 409    | 用户名已被使用，或任务仍在执行、不能删除 |
| 413    | 图片字节数或像素数超过限制               |
| 415    | 图片格式不支持或无法解码                 |
| 422    | 请求字段缺失或不符合约束                 |
| 500    | 数据库操作异常，详细堆栈只留在服务日志里 |

## 调试与验收

[tests/test_main.http](../tests/test_main.http) 提供可直接逐条执行的请求示例。把 `baseUrl` 指向实际地址，用支持 `.http` 的编辑器依次执行即可；脚本会在登录后自动保存令牌、上传后自动保存任务编号。

也可以在服务器上导出实际的 OpenAPI 定义：

```bash
docker compose exec -T api python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/openapi.json').read().decode())"
```

验收顺序为「注册登录 → 上传 → 查询任务和附件 → 翻页 → 改备注 → 删除」。用第二个账号读取第一位用户的记录，确认得到 `404`；浏览器会话另测刷新恢复、退出清除和跨站表单拒绝。
