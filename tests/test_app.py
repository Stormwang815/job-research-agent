from httpx import ASGITransport, AsyncClient

from app.main import app
from app.prompts import build_research_query
from app.models import ResearchRequest


def test_prompt_contains_business_constraints():
    query = build_research_query(ResearchRequest(role="AI Agent工程师", city="北京"))
    assert "AI Agent工程师" in query
    assert "技能矩阵" in query
    assert "禁止虚构URL" in query


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_demo_research_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/research", json={"role": "AI Agent工程师", "demo": True})
        assert created.status_code == 202
        task_id = created.json()["task_id"]
        async with client.stream("GET", f"/api/research/{task_id}/events") as response:
            body = (await response.aread()).decode()
        assert "event: complete" in body
        assert "技能矩阵" in body


async def test_history_contains_persisted_task():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/research", json={"role": "数据分析师", "demo": True})
        response = await client.get("/api/research")
    assert response.status_code == 200
    assert any(item["role"] == "数据分析师" for item in response.json())


async def test_upload_rejects_unsupported_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/documents", files={"file": ("secret.exe", b"x")})
    assert response.status_code == 415


async def test_report_html_is_rendered_and_sanitized():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/research", json={"role": "安全测试工程师<script>alert(1)</script>", "demo": True})
        task_id = created.json()["task_id"]
        async with client.stream("GET", f"/api/research/{task_id}/events") as response:
            await response.aread()
        rendered = await client.get(f"/api/research/{task_id}/report-html")
    assert rendered.status_code == 200
    assert "<h1>" in rendered.text
    assert "<script>" not in rendered.text
