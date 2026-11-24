import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app
from app.models import ResearchRequest
from app.source_quality import curate_sources, score_source
from evals.run_eval import evaluate


def test_whitespace_role_rejected():
    with pytest.raises(ValidationError):
        ResearchRequest(role="   ")


def test_spoofed_source_is_not_trusted():
    assert score_source("https://zhaopin.com.evil.example/job")[1] == 55
    assert score_source("https://jobs.zhaopin.com/job")[1] == 80
    assert curate_sources([{"url": "https://[broken"}, {"url": "https://user:password@example.com"}]) == []


def test_evaluation_reads_markdown_links():
    metrics = evaluate("证据：[招聘](https://example.com/job)\n风险与局限", ["风险与局限"])
    assert metrics["citation_count"] == 1


async def test_two_subscribers_receive_completion():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/research", json={"role": "测试工程师", "demo": True})
        task_id = result.json()["task_id"]
        responses = await asyncio.wait_for(asyncio.gather(
            client.get(f"/api/research/{task_id}/events"),
            client.get(f"/api/research/{task_id}/events"),
        ), timeout=5)
        assert all("event: complete" in response.text for response in responses)
        reconnect = await client.get(f"/api/research/{task_id}/events")
        assert "event: complete" in reconnect.text


async def test_api_authentication_and_cross_site_write(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "test-access-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/research")).status_code == 401
        assert (await client.post("/api/session", json={"token": "wrong"})).status_code == 401
        assert (await client.post("/api/session", json={"token": "test-access-token"})).status_code == 200
        assert (await client.get("/api/research")).status_code == 200
        response = await client.post("/api/research", headers={"Origin": "https://evil.example"}, json={"role": "测试", "demo": True})
        assert response.status_code == 403


async def test_task_capacity(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_TASKS", "0")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/research", json={"role": "测试", "demo": True})
        assert response.status_code == 429
