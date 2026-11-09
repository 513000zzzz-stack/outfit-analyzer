"""请求与响应模型。所有 JSON 接口统一使用 code / message / data 结构。"""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构：业务状态码、结果说明和业务数据。"""

    code: int = Field(description="业务状态码，与 HTTP 状态码保持一致")
    message: str = Field(description="结果说明，成功时为 success 或具体提示")
    data: T | None = Field(default=None, description="业务数据，无返回内容时为 null")


class ValidationIssue(BaseModel):
    loc: list[str | int] = Field(description="出错字段的位置")
    msg: str = Field(description="错误原因")
    type: str = Field(description="错误类型")


class HealthData(BaseModel):
    status: Literal["ok"]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class Note(BaseModel):
    note: str = Field(max_length=1000, description="个人备注，最多 1000 字符")


class UserInfo(BaseModel):
    id: int
    username: str
    bio: str = Field(description="个性签名，注册时写入默认文案")
    avatar: str = Field(description="头像地址，未上传时为空字符串")


class AuthData(BaseModel):
    token: str = Field(description="访问令牌，放在 Authorization 请求头中使用")
    userInfo: UserInfo


class BranchResult(BaseModel):
    status: Literal["ok", "error"]
    seconds: float | None = Field(default=None, description="该方案运行耗时，单位为秒")
    error: str | None = None
    data: dict[str, Any] | None = Field(default=None, description="该方案的结构化结果")


class AnalysisRecord(BaseModel):
    id: str = Field(description="分析任务编号")
    filename: str
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    status: Literal["queued", "running", "completed", "partial", "failed"]
    note: str
    yolo: BranchResult | None
    doubao: BranchResult | None


class HistoryPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    records: list[AnalysisRecord] = Field(alias="list")
    total: int
    has_more: bool = Field(alias="hasMore")


class ErrorResponse(BaseModel):
    """错误响应：参数校验失败时 data 为问题列表，其余情况为 null。"""

    code: int
    message: str
    data: list[ValidationIssue] | None = None
