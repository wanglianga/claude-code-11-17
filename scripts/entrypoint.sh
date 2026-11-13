#!/bin/sh
# 容器入口：等待数据库 -> 建表 -> 幂等装载参考数据 -> 启动 API
set -e

echo "[entrypoint] 等待 PostgreSQL 就绪..."
python - <<'PY'
import time
import psycopg2
import os
from urllib.parse import urlparse

url = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
parsed = urlparse(url)
for i in range(30):
    try:
        psycopg2.connect(
            host=parsed.hostname, port=parsed.port or 5432,
            user=parsed.username, password=parsed.password,
            dbname=parsed.path.lstrip("/"),
        ).close()
        print("[entrypoint] 数据库可连接")
        break
    except Exception as exc:
        print(f"[entrypoint] 未就绪({i+1}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit("数据库等待超时")
PY

echo "[entrypoint] 建表..."
python -m app.cli init-db

echo "[entrypoint] 装载参考数据（幂等）..."
python -m app.cli seed --ref-dir data/reference

echo "[entrypoint] 启动 FastAPI..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
