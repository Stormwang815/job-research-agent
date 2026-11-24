from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    role: str = Field(min_length=2, max_length=80, examples=["AI Agent 开发工程师"])
    city: str = Field(default="全国/远程", max_length=40)
    seniority: Literal["不限", "实习", "初级", "中级", "高级"] = "不限"
    candidate_profile: str = Field(default="", max_length=4000)
    focus: str = Field(default="", max_length=1000)
    source: Literal["web", "local", "hybrid"] = "web"
    demo: bool = False

    @field_validator("role", "city", "candidate_profile", "focus", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ResearchCreated(BaseModel):
    task_id: str


class TaskSummary(BaseModel):
    id: str
    role: str
    city: str
    seniority: str
    status: str
    current_stage: str
    progress: int
    source_count: int
    elapsed_seconds: float
    estimated_cost: float
    created_at: str
    updated_at: str
    error: str
