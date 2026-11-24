import argparse
import asyncio
import os
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_runtime = tempfile.TemporaryDirectory(prefix="job-agent-eval-runtime-")
os.environ.setdefault("DATABASE_PATH", str(Path(_runtime.name) / "runtime.db"))
os.environ.setdefault("REPORT_DIR", str(Path(_runtime.name) / "reports"))

from app.models import ResearchRequest
from app.service import ResearchService


def evaluate(report: str, must_include: list[str]) -> dict:
    section_score = sum(name in report for name in must_include) / len(must_include)
    urls = re.findall(r"https?://[^\s<>\"\)\]]+", report)
    valid_urls = [url for url in urls if urlparse(url).netloc]
    return {
        "section_coverage": round(section_score, 3),
        "citation_count": len(set(valid_urls)),
        "has_limitations": "风险与局限" in report,
    }


async def run(path: Path, live: bool) -> None:
    results = []
    with tempfile.TemporaryDirectory(prefix="job-agent-eval-") as temp_dir:
        service = ResearchService(Path(temp_dir) / "eval.db", recover_interrupted=False)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            request = ResearchRequest(role=case["role"], city=case["city"], seniority=case["seniority"], demo=not live)
            task_id = service.create(request)
            while service.repository.get(task_id)["status"] in {"queued", "running"}:
                await asyncio.sleep(0.1)
            task = service.repository.get(task_id)
            metrics = evaluate(task["report"], case["must_include"]) if task["status"] == "completed" else {"error": task["error"]}
            results.append({"id": case["id"], "task_id": task_id, **metrics})
            print(json.dumps(results[-1], ensure_ascii=False))
    output = Path("evals/results.json")
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存到 {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path("evals/cases.jsonl"))
    parser.add_argument("--live", action="store_true", help="调用真实模型和检索服务，会产生费用")
    args = parser.parse_args()
    asyncio.run(run(args.cases, args.live))
