"""FastAPI entry point for Uvicorn and existing clients."""

from outfit_api.logging_config import configure_logging

configure_logging()

from outfit_api.app import create_app  # noqa: E402  日志需先于应用初始化

app = create_app()
