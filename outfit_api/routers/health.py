from fastapi import APIRouter

from outfit_api.common.responses import ok
from outfit_api.schemas import ApiResponse, HealthData

router = APIRouter(prefix="/api", tags=["服务状态"])


@router.get(
    "/health",
    response_model=ApiResponse[HealthData],
    summary="检查 API 进程是否响应",
)
def health():
    return ok({"status": "ok"})
