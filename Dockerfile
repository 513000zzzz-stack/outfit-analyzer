FROM python:3.11-slim-bookworm AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5
WORKDIR /app

# 初始化共享卷时复制目录和权限，使两个应用进程都能以普通用户写入。
RUN groupadd --gid 10001 outfit && useradd --uid 10001 --gid outfit --create-home outfit \
    && install -d -o outfit -g outfit /var/lib/outfit \
    && install -o outfit -g outfit /dev/null /var/lib/outfit/.volume-init

FROM python-base AS api
COPY requirements/requirements.txt ./
# 缓存挂载让下载过的轮子留在构建机上，构建中断后重试不用重下。
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements.txt
COPY *.py ./
COPY outfit_api/ ./outfit_api/
USER outfit
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM python-base AS worker
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/requirements.txt requirements/requirements-worker.txt ./
# 从国内镜像装 CPU 轮子：既不下载 CUDA 工具包，也不走国外源。
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install torch==2.7.1+cpu torchvision==0.22.1+cpu \
        --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/ \
    && python -m pip install -r requirements-worker.txt
COPY *.py ./
COPY outfit_api/ ./outfit_api/
COPY inference/ ./inference/
ENV YOLO_CONFIG_DIR=/tmp/ultralytics
USER outfit
CMD ["sh", "-c", "exec rq worker --url \"${REDIS_URL:-redis://redis:6379/0}\" outfit"]

FROM python-base AS ui
COPY requirements/requirements-ui.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements-ui.txt
COPY ui.py ./
COPY outfit_ui/ ./outfit_ui/
COPY .streamlit/ .streamlit/
USER outfit
CMD ["python", "-m", "streamlit", "run", "ui.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
