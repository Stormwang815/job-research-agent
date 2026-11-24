import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, SecretStr
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import markdown
import nh3

from app.models import ResearchCreated, ResearchRequest, TaskSummary
from app.config_store import SecretConfigStore
from app.security import SecurityMiddleware
from app.service import DATA_DIR, ROOT, research_service, sse_message

@asynccontextmanager
async def lifespan(app):
    yield
    tasks = list(research_service.running)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="招聘岗位调研 Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(SecurityMiddleware, requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
secret_config = SecretConfigStore(ROOT / ".env")


class SessionRequest(BaseModel):
    token: str


class ProviderConfigRequest(BaseModel):
    openai_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/session")
async def create_session(payload: SessionRequest, response: Response) -> dict[str, bool]:
    expected = os.getenv("APP_ACCESS_TOKEN", "").strip()
    if expected and not secrets.compare_digest(payload.token.encode(), expected.encode()):
        raise HTTPException(401, "访问令牌无效")
    if expected:
        response.set_cookie("job_agent_session", expected, httponly=True, samesite="strict", secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=86400)
    return {"authenticated": True}


@app.get("/api/config/providers")
async def provider_config_status() -> dict[str, bool]:
    status = secret_config.status()
    return {"openai_configured": status["OPENAI_API_KEY"], "tavily_configured": status["TAVILY_API_KEY"]}


@app.put("/api/config/providers")
async def save_provider_config(payload: ProviderConfigRequest) -> dict[str, bool]:
    try:
        status = secret_config.save({
            "OPENAI_API_KEY": payload.openai_api_key.get_secret_value() if payload.openai_api_key else None,
            "TAVILY_API_KEY": payload.tavily_api_key.get_secret_value() if payload.tavily_api_key else None,
        })
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "配置文件无法写入，请检查部署目录权限") from exc
    return {"openai_configured": status["OPENAI_API_KEY"], "tavily_configured": status["TAVILY_API_KEY"]}


@app.get("/api/research", response_model=list[TaskSummary])
async def list_research(limit: int = 30) -> list[dict]:
    return research_service.repository.list(limit)


@app.post("/api/research", response_model=ResearchCreated, status_code=202)
async def create_research(request: ResearchRequest) -> ResearchCreated:
    try:
        return ResearchCreated(task_id=research_service.create(request))
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@app.get("/api/research/{task_id}/events")
async def research_events(task_id: str) -> StreamingResponse:
    state = research_service.get(task_id)
    persisted = research_service.repository.get(task_id)
    if not state and not persisted:
        raise HTTPException(404, "调研任务不存在")
    if not state:
        async def persisted_event():
            event = "complete" if persisted["status"] == "completed" else "error"
            data = {"report": persisted["report"], "report_url": f"/api/research/{task_id}/report"} if event == "complete" else {"message": persisted["error"]}
            yield sse_message(event, data)
        return StreamingResponse(persisted_event(), media_type="text/event-stream")

    async def events():
        yield sse_message("connected", {"task_id": task_id})
        if state.status == "completed":
            yield sse_message("complete", {"report": state.report, "report_url": f"/api/research/{task_id}/report"})
            return
        if state.status == "failed":
            yield sse_message("error", {"message": state.error})
            return
        cursor = 0
        while True:
            async with state.changed:
                if cursor >= len(state.events):
                    try:
                        await asyncio.wait_for(state.changed.wait(), timeout=15)
                    except TimeoutError:
                        pass
                pending = state.events[cursor:]
                cursor = len(state.events)
            if not pending:
                yield ": keep-alive\n\n"
            for item in pending:
                yield sse_message(item["event"], item["data"])
                if item["event"] in {"complete", "error"}:
                    return

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/research/{task_id}/report", response_class=PlainTextResponse)
async def get_report(task_id: str) -> PlainTextResponse:
    state = research_service.get(task_id)
    if state and state.status == "completed":
        return PlainTextResponse(state.report, media_type="text/markdown; charset=utf-8")
    persisted = research_service.repository.get(task_id)
    if persisted and persisted["status"] == "completed":
        return PlainTextResponse(persisted["report"], media_type="text/markdown; charset=utf-8")
    raise HTTPException(404, "报告尚未生成")


@app.get("/api/research/{task_id}/report-html")
async def get_report_html(task_id: str) -> Response:
    task = research_service.repository.get(task_id)
    if not task or task["status"] != "completed":
        raise HTTPException(404, "报告尚未生成")
    rendered = markdown.markdown(task["report"], extensions=["tables", "fenced_code", "sane_lists"])
    safe_html = nh3.clean(rendered, link_rel="noopener noreferrer")
    return Response(safe_html, media_type="text/html; charset=utf-8")


@app.get("/api/research/{task_id}")
async def get_research(task_id: str) -> JSONResponse:
    task = research_service.repository.get(task_id)
    if not task:
        raise HTTPException(404, "调研任务不存在")
    return JSONResponse(task)


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict[str, str | int]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".pdf", ".txt", ".md", ".docx"}:
        raise HTTPException(415, "只支持 PDF、TXT、Markdown 和 DOCX")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "文件不能超过10MB")
    stem = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]", "_", Path(file.filename or "document").stem)[:80]
    destination = DATA_DIR / f"{uuid4().hex[:8]}-{stem}{extension}"
    destination.write_bytes(content)
    return {"filename": destination.name, "size": len(content)}
