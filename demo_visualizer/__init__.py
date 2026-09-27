"""记录真实执行边界；不改变模型、历史或工具的控制流。"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Literal

from azure.core.exceptions import ClientAuthenticationError
from openai import APIStatusError, OpenAIError
from openai.types.responses import Response

from demo1.report import mask_opaque_state

Kind = Literal["user", "request", "response", "tool_call", "tool_result", "memory", "reset", "answer", "final", "error"]


@dataclass
class Event:
    kind: Kind
    title: str
    step: int
    at_ms: float
    data: dict[str, object]
    elapsed_ms: float | None = None
    error: bool = False


@dataclass
class Trace:
    demo: Literal[2, 3]
    model: str = "尚未配置"
    path: Path | None = None
    events: list[Event] = field(default_factory=list)
    status: str = "running"
    started: float = field(default_factory=time.perf_counter)
    duration_ms: float = 0
    source: str = "本次实际执行记录"

    def add(
        self, kind: Kind, title: str, step: int = 0, *,
        elapsed_ms: float | None = None, error: bool = False, **data: object,
    ) -> None:
        # 遮蔽后的快照与实际回传的 history 分离，后续 append/reset 不改写旧记录。
        snapshot = {key: mask_opaque_state(value) for key, value in data.items()}
        self.events.append(Event(
            kind, title, step, (time.perf_counter() - self.started) * 1000,
            snapshot, elapsed_ms, error,
        ))
        self.save()

    def save(self) -> None:
        self.duration_ms = (time.perf_counter() - self.started) * 1000
        if self.path is not None:
            from .report import write_trace
            write_trace(self.path, self)

    @contextmanager
    def model_request(
        self, step: int, request: Mapping[str, object],
    ) -> Iterator[Callable[[Response], None]]:
        self.add("request", "发送模型请求", step, request=dict(request))
        started = time.perf_counter()

        def returned(response: Response) -> None:
            self.add(
                "response", "收到模型返回", step,
                response=response.model_dump(mode="json"),
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=response.status != "completed",
            )

        yield returned

    def __enter__(self) -> Trace:
        self.save()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        if exc is None:
            self.status = "completed"
        else:
            self.status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
            if isinstance(exc, APIStatusError):
                message = f"API 请求失败：HTTP {exc.status_code}。请检查端点、权限或配额。"
            elif isinstance(exc, (OpenAIError, ClientAuthenticationError)):
                message = f"认证或网络请求未完成（{type(exc).__name__}）。"
            elif isinstance(exc, (ValueError, RuntimeError)):
                message = str(exc)
            elif isinstance(exc, KeyboardInterrupt):
                message = "用户中断执行；仅保留已观测到的步骤。"
            else:
                message = f"执行中止（{type(exc).__name__}）；请查看终端错误。"
            self.add(
                "error", "执行中止", self.events[-1].step if self.events else 0,
                error=True, message=message,
            )
        self.save()
