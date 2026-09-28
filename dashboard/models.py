"""上报格式和已批准的等权 Task 计量。"""

from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, field_validator


Text = Annotated[str, StringConstraints(max_length=2000)]
ShortText = Annotated[str, StringConstraints(max_length=240)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
EvidenceLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
EvidenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
StableId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")]
ProjectStatus = Literal["planning", "active", "blocked", "review", "complete"]
TaskStatus = Literal["todo", "active", "waiting", "blocked", "done", "failed", "cancelled"]
Acceptance = Literal["not_required", "pending", "accepted", "rejected"]
Glyph = Literal["grid", "book", "receipt", "image", "bookmark", "globe", "monitor"]
Color = Literal["sage", "sand", "plum", "blue", "stone"]
UpdateTone = Literal["todo", "active", "waiting", "blocked", "done", "failed", "review", "complete"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def timezone_date(value: str) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("date must be an ISO8601 string with timezone")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be ISO8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("date must include timezone")
    return value


class Evidence(StrictModel):
    label: EvidenceLabel
    text: EvidenceText


class Child(StrictModel):
    title: Name
    status: TaskStatus = "todo"


class Task(StrictModel):
    id: StableId
    code: ShortText = ""
    title: Name
    status: TaskStatus = "todo"
    verified: bool = False
    acceptance: Acceptance = "not_required"
    goal: Text = Field(default="", description="任务目标：说明要解决的问题、影响的功能或使用场景，以及预期达到的结果。不要只重复任务标题。")
    summary: Text = Field(default="", description="任务截至当前的工作概述：按主要事项分行列出具体做了什么及结果，通常2–5项，简单任务可1项；使用•或编号并以换行分隔。明确区分已完成、进行中及待完成，更新时保留已完成的主要工作。不要只写日期、验收通过或阶段代号，不逐文件/函数罗列代码。验收与测试依据放在evidence，阻塞原因放在blocker。缺少事实时明确说明，不编造；最多2000字符。")
    updatedAt: str | None = None
    blocker: Text | None = None
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    children: list[Child] = Field(default_factory=list, max_length=100)

    @field_validator("updatedAt")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        return timezone_date(value) if value is not None else None

    @model_validator(mode="after")
    def done_requires_evidence(self):
        if self.status == "done" and (not self.verified or not self.evidence):
            raise ValueError("done task requires verified=true and evidence")
        return self


class Wave(StrictModel):
    id: StableId
    name: Name
    defined: bool = True
    acceptance: Acceptance = "not_required"
    tasks: list[Task] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def undefined_has_no_tasks(self):
        if not self.defined and self.tasks:
            raise ValueError("undefined wave cannot contain tasks")
        return self


class Update(StrictModel):
    at: str
    tone: UpdateTone
    text: Text
    detail: Text = ""

    @field_validator("at")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return timezone_date(value)


class Project(StrictModel):
    name: Name
    shortName: ShortText = ""
    description: Text = ""
    summary: Text = ""
    status: ProjectStatus = "planning"
    acceptance: Acceptance = "not_required"
    category: ShortText = ""
    glyph: Glyph = "grid"
    color: Color = "stone"
    currentWave: StableId | None = None
    blocker: Text | None = None
    waves: list[Wave] = Field(default_factory=list, max_length=200)
    updates: list[Update] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent_scope(self):
        wave_ids = [wave.id for wave in self.waves]
        if len(wave_ids) != len(set(wave_ids)):
            raise ValueError("duplicate wave id")
        if self.currentWave is not None and self.currentWave not in wave_ids:
            raise ValueError("currentWave must reference a wave")
        tasks = [task for wave in self.waves for task in wave.tasks]
        if len(tasks) > 5000:
            raise ValueError("too many tasks")
        task_ids = [task.id for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("duplicate task id")
        if self.status == "complete":
            progress = summarize(self)
            unresolved = (self.acceptance in ("pending", "rejected")
                          or any(wave.acceptance in ("pending", "rejected") for wave in self.waves)
                          or any(task.acceptance in ("pending", "rejected")
                                 for task in tasks if task.status != "cancelled"))
            if (progress["total"] == 0 or progress["done"] != progress["total"]
                    or progress["unplannedWaves"] or unresolved):
                raise ValueError("complete project requires completed work and no pending scope or acceptance")
        return self


class Snapshot(StrictModel):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0)
    observed_at: str
    change_note: Text
    project: Project

    @field_validator("observed_at")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return timezone_date(value)


def summarize(project: Project) -> dict:
    tasks = [task for wave in project.waves for task in wave.tasks if task.status != "cancelled"]
    completed = [task for task in tasks if task.status == "done" and task.verified]
    total = len(tasks)
    return {
        "done": len(completed),
        "total": total,
        "percent": (2 * len(completed) * 100 + total) // (2 * total) if total else None,
        "unplannedWaves": sum(not wave.defined for wave in project.waves),
        "pendingAcceptance": (int(project.acceptance == "pending")
                              + sum(wave.acceptance == "pending" for wave in project.waves)
                              + sum(task.acceptance == "pending" for task in completed)),
    }
