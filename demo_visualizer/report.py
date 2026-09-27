"""自包含离线报告：所有数据渲染为转义后的 HTML，脚本只操作 DOM。"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from demo1.report import STYLE as TREE_STYLE, render_json_tree

if TYPE_CHECKING:
    from . import Event, Trace

ASSETS = Path(__file__).parent
LABELS = {
    "user": ("用户", "user"), "request": ("模型请求", "model"),
    "response": ("模型返回", "model"), "tool_call": ("工具调用", "tool"),
    "tool_result": ("工具结果", "tool"), "memory": ("历史写入", "memory"),
    "reset": ("清空记忆", "memory"), "answer": ("本轮回答", "answer"),
    "final": ("最终答案", "answer"), "error": ("执行错误", "error"),
}
EXPLANATIONS = {
    "user": "用户提供目标或新问题。Demo 2 由用户推动下一轮；Demo 3 由程序循环继续。",
    "request": "这里是实际发送的请求正文。input 携带完整历史；instructions 每轮生效。没有记录认证头。",
    "response": "这是 API 的完整返回，不只是回答文本。output 中的 function_call 是行动请求，尚不是工具执行结果。",
    "tool_call": "模型只决定工具名和参数。Python 白名单分派器负责校验并执行；同一批工具在本地依次执行。",
    "tool_result": "这是本地工具的真实返回。通过 call_id 与模型请求配对，随后作为 function_call_output 加入历史。",
    "memory": "将完整输出或工具反馈追加到本地 history。下一次请求的 input 才会将这些内容反馈给模型。",
    "reset": "清空的是会话上下文，不是观测记录，也不重置 API 调用预算。下一轮不再携带旧历史。",
    "answer": "从本轮 output 提取助手文字。对话不会自行行动；等待下一条用户输入。",
    "final": "模型不再请求工具，并返回非空文本；程序退出 Loop。这是终止条件，不是固定轮数。",
    "error": "本次运行未正常完成。已记录的调用和中间结果仍保留，但不会冒充最终成功。",
}


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def answer_html(value: object) -> str:
    """只增强粗体与行内代码；不接受原始 HTML、链接或图片。"""
    return re.sub(
        r"\*\*([^\n]+?)\*\*|`([^`\n]+)`",
        lambda match: (
            f"<strong>{match.group(1)}</strong>" if match.group(1) is not None
            else f"<code>{match.group(2)}</code>"
        ),
        escape(value),
    )


def panel(title: str, value: object) -> str:
    return (
        f'<section class="payload"><h3>{escape(title)}</h3>'
        '<p class="tree-help">展开查看结构 · 悬停字段查看路径 · 加密推理状态已遮蔽</p>'
        f'{render_json_tree(value)}</section>'
    )


def history_strip(items: object) -> str:
    if not isinstance(items, list):
        return ""
    chips = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("type", "item")
        call_id = item.get("call_id", "")
        chips.append(
            f'<span class="history-chip" title="{escape(call_id)}">'
            f'<b>{index + 1:02d}</b> {escape(role)}</span>'
        )
    return (
        f'<div class="history-strip"><span class="mini-label">{len(items)} 个上下文项</span>'
        + ("".join(chips) or '<span class="muted">空历史，从新对话开始</span>') + "</div>"
    )


def event_body(event: Event, trace: Trace) -> str:
    data = event.data
    body = f'<p class="explanation">{EXPLANATIONS[event.kind]}</p>'
    if event.kind in {"user", "answer", "final", "error"}:
        text = data.get("text", data.get("message", ""))
        rendered = answer_html(text) if event.kind in {"answer", "final"} else escape(text)
        body += f'<div class="event-text">{rendered}</div>'
        if "history_items" in data:
            body += f'<p class="muted">本轮携带旧历史：{escape(data["history_items"])} 项。</p>'
    if event.kind == "request":
        request = data.get("request")
        if isinstance(request, dict):
            body += history_strip(request.get("input"))
        body += panel("实际请求 / REQUEST", request)
    elif event.kind == "response":
        response = data.get("response")
        if isinstance(response, dict):
            outputs = response.get("output", [])
            body += history_strip(outputs)
            if isinstance(outputs, list):
                names = [item.get("name", "") for item in outputs
                         if isinstance(item, dict) and item.get("type") == "function_call"]
                if names:
                    body += f'<p class="callout">本轮请求 {len(names)} 个工具：{escape(" → ".join(map(str, names)))}。此时尚未执行。</p>'
            body += panel("完整返回 / RESPONSE", response)
    elif event.kind in {"memory", "reset"}:
        body += (
            '<div class="memory-change">'
            f'<strong>{escape(data.get("before"))}</strong><span>→</span>'
            f'<strong>{escape(data.get("after"))}</strong><small>history 项，不是 token 数</small></div>'
        )
        body += history_strip(data.get("history"))
        body += panel("此刻的完整历史快照", data.get("history"))
    elif event.kind in {"tool_call", "tool_result"}:
        call_id = data.get("call_id")
        body += f'<div class="call-id"><span>CALL ID</span><code>{escape(call_id)}</code>'
        for index, other in enumerate(trace.events):
            if (other.step == event.step and other.data.get("call_id") == call_id
                    and other.kind in {"tool_call", "tool_result"} and other.kind != event.kind):
                body += f'<a class="jump" href="#event-{index}">跳到对应{"结果" if other.kind == "tool_result" else "调用"} ↗</a>'
        body += "</div>"
        if event.kind == "tool_call":
            arguments = data.get("arguments")
            if isinstance(arguments, str):
                try:
                    decoded = json.loads(arguments)
                except ValueError:
                    body += '<p class="callout error-note">参数不是有效 JSON；分派器将返回可观测的校验错误。</p>'
                else:
                    body += panel("解析后的工具参数", decoded)
            body += panel("原始调用字段", data)
        else:
            body += panel("工具返回结构", data.get("output"))
    return body


def flow_diagram(demo: int) -> str:
    if demo == 3:
        nodes = [("user", 10, "用户任务", "设定目标"), ("memory", 230, "History", "保存输入与反馈"),
                 ("model", 450, "语言模型", "选择行动 / 回答"), ("tool", 670, "工具执行", "Python · 顺序分派"),
                 ("answer", 900, "最终答案", "无工具请求时退出")]
        paths = (
            '<path d="M190 97H225"/><path d="M410 97H445"/><path d="M630 97H665"/>'
            '<path d="M540 60V25H990V60"/><path class="loop-path" d="M760 136V184H320V138"/>'
        )
        captions = (
            '<text x="765" y="17">无工具请求 + 非空回答</text>'
            '<text x="540" y="174">LOOP ↺ 工具结果 → 完整历史 → 下一轮请求</text>'
        )
    else:
        nodes = [("user", 40, "用户消息", "每轮新的输入"), ("memory", 310, "History", "旧历史 + 新问题"),
                 ("model", 580, "语言模型", "读取上下文"), ("answer", 850, "本轮回答", "保存完整输出")]
        paths = (
            '<path d="M220 97H305"/><path d="M490 97H575"/><path d="M760 97H845"/>'
            '<path class="loop-path" d="M940 136V184H400V138"/>'
        )
        captions = '<text x="670" y="174">保存完整输出；等待用户下一句，再携带历史请求</text>'
    boxes = "".join(
        f'<g class="flow-node" data-node="{kind}"><rect x="{x}" y="61" width="180" height="75" rx="13"/>'
        f'<text class="node-title" x="{x + 90}" y="92">{title}</text>'
        f'<text class="node-caption" x="{x + 90}" y="114">{caption}</text></g>'
        for kind, x, title, caption in nodes
    )
    return (
        '<div class="flow-scroll"><svg class="flow" viewBox="0 0 1100 205" role="img" '
        f'aria-label="{"模型调用工具，结果返回历史后再次请求模型，直到最终回答" if demo == 3 else "用户消息与历史传给模型，回答保存后等待下一轮"}">'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0 0L10 5L0 10Z" fill="#7492b3"/></marker></defs>'
        f'<g class="flow-edges">{paths}</g><g class="flow-labels">{captions}</g>{boxes}</svg></div>'
    )


def round_cards(trace: Trace) -> str:
    cards = []
    for index, event in enumerate(trace.events):
        if event.kind != "request":
            continue
        tools = [item for item in trace.events if item.step == event.step and item.kind == "tool_call"]
        response = next((item for item in trace.events if item.step == event.step and item.kind == "response"), None)
        answered = any(item.step == event.step and item.kind in {"answer", "final"} for item in trace.events)
        ending = ("本轮回答 · 等待下一条用户消息" if trace.demo == 2 else "最终回答 · 退出 Loop") if answered else "处理返回 / 尚无有效答案"
        returned = "等待返回 / 未收到返回" if response is None else (
            "非完整返回" if response.error else " → ".join(str(item.data["name"]) for item in tools) or ending
        )
        cards.append(
            f'<a class="round-card jump" href="#event-{index}"><span>ROUND {event.step:02d}</span>'
            f'<strong>{escape(returned)}</strong><small>'
            f'{f"{response.elapsed_ms:,.0f} ms" if response is not None and response.elapsed_ms is not None else "耗时未报告"}'
            f' · {len(tools)} 次工具调用</small></a>'
        )
    return '<div class="rounds">' + "".join(cards) + "</div>"


def usage_total(trace: Trace, key: str) -> str:
    total = count = responses = 0
    for event in trace.events:
        if event.kind != "response":
            continue
        responses += 1
        response = event.data.get("response")
        usage = response.get("usage") if isinstance(response, dict) else None
        value = usage.get(key) if isinstance(usage, dict) else None
        if type(value) is int and value >= 0:
            total += value
            count += 1
    if not count:
        return "未报告"
    coverage = f"（仅 {count}/{responses} 个返回已报告）" if count < responses else ""
    return f"{total:,}{coverage}"


def write_trace(path: Path, trace: Trace) -> None:
    css = (ASSETS / "report.css").read_text(encoding="utf-8")
    script = (ASSETS / "report.js").read_text(encoding="utf-8")
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    title = "让对话记住上下文。" if trace.demo == 2 else "看见 Agent 的每一次行动。"
    subtitle = (
        "从第一句到最后一轮，沿着历史的增长，理解短期记忆从何而来。没有工具，也没有自动 Agent Loop。"
        if trace.demo == 2 else
        "目标如何变成行动，工具结果如何回到模型，循环何时停止。这里的每一步，都来自程序实际记录的执行边界。"
    )
    status = {"running": "执行中 · 刷新查看新记录", "completed": "运行完成",
              "failed": "运行失败 · 保留部分轨迹", "interrupted": "运行中断"}.get(trace.status, trace.status)
    requests = sum(event.kind == "request" for event in trace.events)
    tools = sum(event.kind == "tool_call" for event in trace.events)
    errors = sum(event.error for event in trace.events)
    metrics = [
        ("模型请求", str(requests), "每轮完整回传上下文"),
        ("工具执行", str(tools), "本地顺序执行" if trace.demo == 3 else "本课不使用工具"),
        ("已报告输入 / 输出 tokens", f'{usage_total(trace, "input_tokens")} / {usage_total(trace, "output_tokens")}', "各次返回用量之和，重复历史重复计入"),
        ("总运行耗时", f"{trace.duration_ms / 1000:,.2f} s", f"{len(trace.events)} 个事件 · {errors} 个异常事件"),
    ]
    metrics_html = "".join(
        f'<div class="stat"><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(note)}</small></div>'
        for label, value, note in metrics
    )
    answers = [(index, event) for index, event in enumerate(trace.events) if event.kind in {"answer", "final"}]
    answer_title = "最后一轮回答" if trace.demo == 2 else "最终答案"
    if answers:
        _, answer = answers[-1]
        answer_text = str(answer.data.get("text", ""))
        if trace.status in {"failed", "interrupted"}:
            answer_title = "此前已完成的回答（本次运行未完成）"
    else:
        answer_text = "尚未获得回答。请查看执行轨迹和错误状态；工具中间结果不等于最终答案。"
    answer_history = "".join(
        f'<details class="answer-turn"><summary>第 {event.step} 轮 · 查看完整回答</summary>'
        f'<div class="event-text">{answer_html(event.data.get("text", ""))}</div>'
        f'<a class="jump" href="#event-{index}">定位此轮事件 ↗</a></details>'
        for index, event in answers[:-1]
    )
    last_error = next((event for event in reversed(trace.events) if event.kind == "error"), None)
    failure = (
        f'<div class="failure" role="alert"><strong>{escape(status)}</strong>'
        f'<p>{escape(last_error.data.get("message"))}</p></div>' if last_error else ""
    )
    navigation, panels = [], []
    for index, event in enumerate(trace.events):
        label, group = LABELS[event.kind]
        navigation.append(
            f'<a class="event-link" href="#event-{index}" data-index="{index}" data-group="{group}" '
            f'data-error="{str(event.error).lower()}"><span class="event-number">{index + 1:02d}</span>'
            f'<span><small>R{event.step:02d} · {label} · +{event.at_ms / 1000:.2f}s</small>'
            f'<strong>{escape(event.title)}</strong></span>'
            f'{"<span class=error-dot aria-label=异常>!</span>" if event.error else ""}</a>'
        )
        duration = f" · {event.elapsed_ms:,.1f} ms" if event.elapsed_ms is not None else ""
        panels.append(
            f'<article class="event-panel{" has-error" if event.error else ""}" id="event-{index}" data-node="{group}">'
            f'<div class="event-heading"><div><span class="eyebrow">EVENT {index + 1:02d} / ROUND {event.step:02d}{duration}</span>'
            f'<h2>{escape(event.title)}</h2></div><span class="tag">{label}</span></div>'
            f'{event_body(event, trace)}</article>'
        )
    empty = '<p class="empty-trace">尚无调用记录；请检查配置或输入消息。</p>' if not trace.events else ""
    filters = "".join(
        f'<option value="{value}">{label}</option>'
        for value, label in (("all", "全部事件"), ("model", "模型请求 / 返回"), ("tool", "工具调用 / 结果"),
                             ("memory", "历史 / 重置"), ("errors", "异常事件"))
    )
    page = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f'script-src \'sha256-{digest}\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        f'<title>Demo {trace.demo} · 调用流程可视化</title><style>{TREE_STYLE}\n{css}</style></head><body><main>'
        '<div class="topbar"><span class="brand"><i></i> AI QUICK LEARN <b>/ OBSERVATORY</b></span>'
        f'<span class="run-status {escape(trace.status)}">{escape(status)}</span></div>'
        f'<header class="hero"><span class="eyebrow">DEMO 0{trace.demo} / {"CONVERSATION MEMORY" if trace.demo == 2 else "AGENT LOOP"}</span>'
        f'<h1>{title}</h1><p class="intro">{subtitle}</p>'
        f'<div class="run-meta"><span>{escape(trace.source)}</span><span>{escape(trace.model)}</span>'
        '<span>Responses API · store=False</span></div></header>'
        f'{failure}<section class="stats" aria-label="运行概览">{metrics_html}</section>'
        '<section class="flow-board"><div class="section-head"><div><span class="eyebrow">THE BIG PICTURE</span>'
        '<h2>调用路径与循环</h2></div><p>选择下方事件，流程节点同步高亮</p></div>'
        f'{flow_diagram(trace.demo)}{round_cards(trace)}</section>'
        '<section class="result-board"><div><span class="eyebrow">THE OUTCOME</span>'
        f'<h2>{answer_title}</h2><p class="muted">{"全部轮次的回答也保留在轨迹中。" if trace.demo == 2 else "由模型停止工具调用后给出；不伪造结束状态。"}</p></div>'
        f'<div><div class="result-text">{answer_html(answer_text)}</div>{answer_history}</div></section>'
        '<section class="trace-workspace" aria-label="逐步调用轨迹"><div class="section-head"><div>'
        '<span class="eyebrow">UNDER THE HOOD</span><h2>逐步拆解执行现场</h2></div>'
        '<p>回放已有记录，不会重新调用 API</p></div>'
        '<div class="playback" hidden><button id="previous" type="button" aria-label="上一步">←</button>'
        '<button id="play" type="button">播放轨迹</button><button id="next" type="button" aria-label="下一步">→</button>'
        f'<label class="scrubber">步骤 <input id="seek" type="range" min="0" max="{max(0, len(trace.events) - 1)}" value="0" aria-label="选择事件"></label>'
        '<output id="position" aria-live="polite"></output>'
        '<label class="speed">速度 <select id="speed"><option value="1800">1×</option><option value="900">2×</option><option value="3600">0.5×</option></select></label>'
        '<button id="expand" type="button">展开当前 JSON</button></div>'
        '<div class="workspace-grid"><aside class="timeline"><div class="timeline-head"><strong>执行时间线</strong>'
        f'<label class="filter-control" hidden><span class="sr-only">筛选事件</span><select id="filter">{filters}</select></label></div>'
        f'<nav aria-label="调用事件">{"".join(navigation)}</nav><p id="no-matches" hidden>没有匹配事件</p></aside>'
        f'<div class="inspector">{empty}{"".join(panels)}</div></div></section>'
        '<footer><strong>如何读图</strong> · 时间线是实际执行顺序，不是模型内部思维链。'
        '一轮 API 可以请求多个工具，工具名称与 call_id 可在调用和结果间跳转。'
        '图中闭环说明控制流；轮次卡片与事件详情显示本次真正走过的路径。'
        '<br>报告每步更新，运行中请刷新浏览器。离线回放只切换现有记录；不联网、不执行工具。'
        '缺失用量不补零，加密推理内容已遮蔽；输入、输出及工具结果仍可能敏感，分享前请检查。'
        '<br>没有 JavaScript 时仍可按顺序阅读全部事件并展开 JSON 树。</footer>'
        f'</main><script>{script}</script></body></html>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # 浏览器刷新与模型请求可以同时发生，只让读者看到一份完整快照。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(page)
        except OSError:
            output.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
