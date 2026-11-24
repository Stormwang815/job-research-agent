import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

from app.models import ResearchRequest
from app.prompts import build_research_query
from app.database import TaskRepository
from app.source_quality import curate_sources

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = Path(os.getenv("REPORT_DIR", str(ROOT / "reports")))
REPORT_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
DATA_DIR.mkdir(exist_ok=True)
if os.getenv("LOAD_DOTENV", "true").lower() == "true":
    load_dotenv(dotenv_path=ROOT / ".env")


@dataclass
class TaskState:
    request: ResearchRequest
    events: list[dict[str, Any]] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    status: str = "queued"
    report: str = ""
    error: str = ""


class ResearchService:
    def __init__(self, database_path: Path | None = None, recover_interrupted: bool = True) -> None:
        self.tasks: dict[str, TaskState] = {}
        database_path = database_path or Path(os.getenv("DATABASE_PATH", "./var/job_research.db"))
        if not database_path.is_absolute():
            database_path = ROOT / database_path
        self.repository = TaskRepository(database_path, recover_interrupted=recover_interrupted)
        self.running: set[asyncio.Task] = set()

    def create(self, request: ResearchRequest) -> str:
        if len(self.running) >= int(os.getenv("MAX_ACTIVE_TASKS", "2")):
            raise RuntimeError("当前调研任务已满，请等待任务完成后重试")
        task_id = uuid4().hex[:12]
        self.tasks[task_id] = TaskState(request=request)
        self.repository.create(task_id, request.model_dump())
        task = asyncio.create_task(self._run(task_id))
        self.running.add(task)
        task.add_done_callback(self.running.discard)
        return task_id

    def get(self, task_id: str) -> TaskState | None:
        return self.tasks.get(task_id)

    async def _emit(self, state: TaskState, event: str, **data: Any) -> None:
        async with state.changed:
            state.events.append({"event": event, "data": data})
            state.changed.notify_all()

    async def _run(self, task_id: str) -> None:
        state = self.tasks[task_id]
        started = time.monotonic()
        state.status = "running"
        self.repository.update(task_id, status="running", current_stage="prepare", progress=8)
        await self._emit(state, "progress", stage="prepare", message="正在生成岗位调研任务…", percent=8)
        try:
            if state.request.demo:
                report, sources, cost = await self._demo_run(state)
            else:
                async with asyncio.timeout(int(os.getenv("RESEARCH_TIMEOUT_SECONDS", "900"))):
                    report, sources, cost = await self._live_run(state)

            elapsed = round(time.monotonic() - started, 2)
            curated = curate_sources(sources)
            report = self._append_run_metadata(report, task_id, elapsed, len(curated), cost)
            output = REPORT_DIR / f"{task_id}.md"
            output.write_text(report, encoding="utf-8")
            state.report = report
            state.status = "completed"
            self.repository.add_sources(task_id, curated)
            self.repository.update(task_id, status="completed", current_stage="complete", progress=100, report=report, source_count=len(curated), elapsed_seconds=elapsed, estimated_cost=cost)
            await self._emit(
                state,
                "complete",
                report=report,
                report_url=f"/api/research/{task_id}/report",
                elapsed_seconds=elapsed,
                source_count=len(curated),
                estimated_cost=cost,
            )
        except asyncio.CancelledError:
            state.status = "failed"
            state.error = "任务因服务关闭而中断，请重新运行"
            self.repository.update(task_id, status="failed", current_stage="error", progress=100, error=state.error)
            raise
        except Exception as exc:
            state.status = "failed"
            state.error = self._friendly_error(exc)
            self.repository.update(task_id, status="failed", current_stage="error", progress=100, error=state.error)
            await self._emit(state, "error", message=state.error)
        finally:
            # Reports remain in SQLite; release large in-memory task state.
            self.tasks.pop(task_id, None)

    async def _live_run(self, state: TaskState) -> tuple[str, list[Any], float]:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("缺少 OPENAI_API_KEY。请复制 .env.example 为 .env 并填写密钥，或勾选演示模式。")
        if state.request.source != "local" and os.getenv("RETRIEVER", "tavily").lower() == "tavily" and not os.getenv("TAVILY_API_KEY"):
            raise RuntimeError("当前检索器是 Tavily，但缺少 TAVILY_API_KEY。请在 .env 中配置，或勾选演示模式。")

        from gpt_researcher import GPTResearcher

        await self._emit(state, "progress", stage="research", message="正在拆解问题并检索岗位信息…", percent=20)
        self.repository.update(self._task_id_for(state), current_stage="research", progress=20)
        researcher = GPTResearcher(
            query=build_research_query(state.request),
            report_type="research_report",
            report_source=state.request.source,
            tone="Objective",
            verbose=False,
        )
        await researcher.conduct_research()
        sources = list(getattr(researcher, "research_sources", []) or [])
        await self._emit(
            state,
            "progress",
            stage="write",
            message=f"检索完成，正在综合 {len(sources)} 条来源…",
            percent=72,
        )
        self.repository.update(self._task_id_for(state), current_stage="write", progress=72)
        report = await researcher.write_report(
            custom_prompt="请完全遵守用户任务中规定的中文报告章节、证据边界和引用要求。"
        )
        cost = float(getattr(researcher, "research_costs", 0.0) or 0.0)
        return report, sources, cost

    async def _demo_run(self, state: TaskState) -> tuple[str, list[Any], float]:
        await asyncio.sleep(0.15)
        await self._emit(state, "progress", stage="research", message="演示：正在检索岗位样本…", percent=35)
        self.repository.update(self._task_id_for(state), current_stage="research", progress=35)
        await asyncio.sleep(0.15)
        await self._emit(state, "progress", stage="write", message="演示：正在生成技能矩阵与行动计划…", percent=75)
        self.repository.update(self._task_id_for(state), current_stage="write", progress=75)
        role = state.request.role
        city = state.request.city
        report = f"""# {role}岗位调研报告（演示数据）

> 当前为演示模式，以下内容用于验证产品流程，不代表真实市场调研结论。

## 1. 执行摘要

本报告演示了针对{city}的{role}岗位调研结果结构。启用真实模式后，系统将检索公开招聘信息并生成带来源的分析。

## 2. 岗位画像

- 将自然语言需求转化为可执行的 Agent 工作流。
- 开发工具调用、检索增强与状态管理能力。
- 通过评测集持续检查系统的正确性、成本和稳定性。

## 3. 技能矩阵

| 技能 | 重要程度 | 证据状态 | 候选人现状 | 差距 |
|---|---|---|---|---|
| Python/FastAPI | 高 | 演示数据 | 待补充 | 无法判断 |
| Tool Calling | 高 | 演示数据 | 待补充 | 无法判断 |
| RAG与检索 | 中高 | 演示数据 | 待补充 | 无法判断 |
| Agent评测 | 中高 | 演示数据 | 待补充 | 无法判断 |

## 4. 市场需求证据

演示模式不访问网络，因此不生成市场比例或伪造引用。真实模式会在这里展示来自招聘页面和官方资料的证据。

## 5. 候选人差距分析

候选人背景：{state.request.candidate_profile or '未提供，无法判断个人差距。'}

## 6. 8周行动计划

1. 第1—2周：完成岗位数据采集，验收标准为输出结构化岗位样本。
2. 第3—4周：实现检索与来源追踪，验收标准为所有关键结论均有链接。
3. 第5—6周：加入失败重试和成本统计，验收标准为测试任务可重复执行。
4. 第7—8周：建立评测集并部署，验收标准为README包含可复现实验结果。

## 7. 简历项目建议

开发招聘岗位调研 Agent，包含任务拆解、网页检索、技能提取、候选人匹配与报告生成；记录来源数、耗时和模型成本。

## 8. 风险与局限

演示内容不是实时数据。真实研究仍可能受到招聘网站可访问性、样本偏差和模型错误影响。

## 9. 引用来源

演示模式无外部来源。
"""
        return report, [], 0.0

    def _task_id_for(self, state: TaskState) -> str:
        return next(task_id for task_id, candidate in self.tasks.items() if candidate is state)

    @staticmethod
    def _append_run_metadata(report: str, task_id: str, elapsed: float, source_count: int, cost: float) -> str:
        created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return (
            report.rstrip()
            + "\n\n---\n\n"
            + f"运行记录：`{task_id}` · {created} · {elapsed}s · {source_count}条来源 · 估算成本 ${cost:.4f}\n"
        )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "调研超时，请缩小范围后重试"
        message = str(exc).strip()
        if isinstance(exc, RuntimeError) and message.startswith(("缺少 OPENAI_API_KEY", "当前检索器是 Tavily")):
            return message
        return "调研失败，请检查模型和搜索服务配置后重试（" + exc.__class__.__name__ + "）"


def sse_message(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


research_service = ResearchService()
