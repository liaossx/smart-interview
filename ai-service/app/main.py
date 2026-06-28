"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.interview import router as interview_router
from app.api.v1.routes.resume import router as resume_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_application() -> FastAPI:
    app = FastAPI(
        title="SmartInterview AI",
        description="智能面试模拟 Agent 服务",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    # CORS — 从配置读取允许的来源
    settings = get_settings()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(interview_router, prefix="/api/v1")
    app.include_router(resume_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_application()
