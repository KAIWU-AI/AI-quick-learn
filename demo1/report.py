"""离线双 API 仪表盘：保留 JSON 结构，同时解释两种不同的返回语义。"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai.types.responses import Response


@dataclass
class CallResult:
    provider: str
    protocol: str
    request: dict[str, object]
    response: dict[str, object] | None = None
    answer: str = ""
    elapsed_ms: float | None = None
    error: str | None = None


HINTS = {
    "model": "模型或部署标识，不代表质量排名",
    "input": "交给模型的输入",
    "instructions": "指导模型如何回答的指令",
    "output": "输出项目数组，不仅包含最终文字",
    "content": "消息内部的内容片段",
    "text": "消息内容中的 text 是正文；响应顶层 text 是输出格式配置",
    "usage": "服务报告的用量；不同 API 的计量口径可能不同",
    "input_tokens": "服务报告的输入 token 数",
    "output_tokens": "服务报告的输出 token 数；可能包含推理 token",
    "reasoning": "推理相关元数据，不等于完整内部思考过程",
    "state": "传给 JEV 的应用状态或证据；本例包含待判断的工单，不是服务运行状态",
    "document": "待分析的文档内容",
    "questions": "要求服务回答的结构化问题",
    "criteria": "分类或判断所依据的标准",
    "answers": "按问题组织的结构化答案",
    "category": "问题在代码中的标识，用于对应 questions 与 answers",
    "choice": "服务选择的类别，不是自由生成的回答正文",
    "confidence": "服务提供的 confidence 表示选项分布的集中程度，不是事实正确率",
    "probabilities": "服务提供的竞争选项概率，用于比较各选项，不等同于 confidence",
    "encrypted_content": "不透明的加密内容已遮蔽，不展示或解读",
    "tools": "提供给模型的工具定义，不等于这些工具已经执行",
    "arguments": "模型生成的工具参数字符串，执行前仍需解析和校验",
    "call_id": "将一次工具调用与对应的 function_call_output 结果配对",
    "store": "是否在服务端存储此响应；false 不表示服务商没有日志",
    "include": "额外请求的返回字段；加密推理状态仍是不透明的",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def mask_opaque_state(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "[已遮蔽 encrypted_content]" if key == "encrypted_content" else mask_opaque_state(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_opaque_state(item) for item in value]
    return value


def _tree(value: object, key: str = "$", path: str = "$", depth: int = 0) -> str:
    hint = f'<span class="hint">{_escape(HINTS[key])}</span>' if key in HINTS else ""
    label = f'<span class="key">{_escape(key)}</span>'
    if isinstance(value, (dict, list)):
        kind = "object" if isinstance(value, dict) else "array"
        size = len(value)
        pairs = value.items() if isinstance(value, dict) else enumerate(value)
        children = []
        for child_key, item in pairs:
            segment = json.dumps(str(child_key), ensure_ascii=False) if kind == "object" else str(child_key)
            children.append(_tree(item, str(child_key), f"{path}[{segment}]", depth + 1))
        empty_label = "空对象 {}" if kind == "object" else "空数组 []"
        content = "".join(children) or f'<li class="empty">{empty_label}</li>'
        opened = " open" if depth < 2 else ""
        return (
            f'<li><details class="branch"{opened}><summary title="{_escape(path)}">'
            f'{label}<span class="badge">{kind} · {size}</span>{hint}</summary>'
            f'<ul class="children">{content}</ul></details></li>'
        )
    if value is None:
        kind, literal = "null", "null"
    elif isinstance(value, bool):
        kind, literal = "boolean", "true" if value else "false"
    elif isinstance(value, (int, float)):
        kind, literal = "number", str(value)
    else:
        kind, literal = "string", json.dumps(value, ensure_ascii=False)
    return (
        f'<li class="leaf" title="{_escape(path)}">{label}<span class="colon">:</span>'
        f'<span class="scalar {kind}">{_escape(literal)}</span>'
        f'<span class="badge">{kind}</span>{hint}</li>'
    )


def _json_panel(title: str, data: dict[str, object]) -> str:
    return (
        f'<section class="json-panel"><h3>{_escape(title)}</h3>'
        '<p class="tree-help">点击三角展开对象或数组 · 悬停字段查看完整路径</p>'
        f'{render_json_tree(data)}</section>'
    )


def render_json_tree(value: object) -> str:
    """供各课复用同一套转义、字段解读和加密状态遮蔽规则。"""
    return f'<ul class="tree">{_tree(mask_opaque_state(value))}</ul>'


def _metric(label: str, value: object) -> str:
    return f'<div class="metric"><dt>{_escape(label)}</dt><dd>{_escape(value)}</dd></div>'


def _probabilities(response: dict[str, object]) -> str:
    answers = response.get("answers")
    category = answers.get("category") if isinstance(answers, dict) else None
    if not isinstance(category, dict):
        return ""
    rows = []
    probabilities = category.get("probabilities")
    if isinstance(probabilities, dict):
        for label, value in probabilities.items():
            if type(value) not in (int, float) or not 0 <= value <= 1:
                rows.append(f'<p class="muted">{_escape(label)}：值不在有效概率范围内，请查看 JSON。</p>')
                continue
            # Decimal 避免把 0.29 显示成 28.999999…%；宽度只接受已验证的数字。
            percent = format(Decimal(str(value)) * 100, "f")
            if "." in percent:
                percent = percent.rstrip("0").rstrip(".")
            rows.append(
                f'<div class="probability"><div class="bar-label"><span>{_escape(label)}</span>'
                f'<strong>{percent}%</strong></div><div class="bar" role="meter" '
                f'aria-label="{_escape(label)}：服务提供的概率" aria-valuemin="0" '
                f'aria-valuemax="100" aria-valuenow="{percent}" aria-valuetext="{percent}%">'
                f'<span style="width:{percent}%"></span></div></div>'
            )
    confidence = ""
    if "confidence" in category:
        value = json.dumps(mask_opaque_state(category["confidence"]), ensure_ascii=False)
        confidence = (
            f'<p class="confidence">服务提供的 confidence：<strong>{_escape(value)}</strong><br>'
            'confidence 表示选项分布的集中程度，不是事实正确率，也不保证工作流正确。</p>'
        )
    if not rows and not confidence:
        return ""
    return (
        '<section class="distribution"><h3>类别分布</h3>'
        '<p class="muted">probabilities 比较相互竞争的选项；原样呈现服务概率（× 100%），'
        '不重新归一化，不等于 confidence 或事实准确率。</p>'
        + "".join(rows) + confidence + "</section>"
    )


def _provider(call: CallResult, index: int) -> str:
    response = call.response
    data = response if response is not None else {}
    status = data.get("status", "已收到返回")
    error = call.error
    if error is None and response is None:
        error = "未收到 API 返回 JSON。"
    if error is None and isinstance(status, str) and status.lower() in {
        "failed", "error", "incomplete", "cancelled", "canceled",
    }:
        error = f"服务返回非成功状态：{status}"
    if not isinstance(status, (str, int, float, bool)) and status is not None:
        status = "结构化状态，见返回树"
    metrics = _metric("模型 / 部署", data.get("model") or call.request.get("model") or "未报告")
    metrics += _metric("状态", "调用失败" if error is not None else status)
    latency = call.elapsed_ms
    latency_text = f"{latency:,.1f} ms" if latency is not None and math.isfinite(latency) and latency >= 0 else "未报告"
    metrics += _metric("本次耗时", latency_text)
    usage = data.get("usage")
    for key, label in (("input_tokens", "输入 tokens"), ("output_tokens", "输出 tokens")):
        value = usage.get(key) if isinstance(usage, dict) else None
        metrics += _metric(label, value if value is not None else "未提供")
    is_jev = call.provider.upper() == "JEV"
    semantics = (
        "TypeSafe：document + questions / criteria → answers。choice 是选中的类别；"
        "probabilities 比较竞争选项。confidence 表示选项分布的集中程度，不是事实正确率。"
        "不把 choice 当作 LLM 正文，也不假设 LLM 提供可比的 confidence。"
        if is_jev else
        "Responses：input + instructions → output。output_text 是从消息内容提取的文字，不是完整返回对象。"
    )
    notice = ""
    if error is not None:
        notice = f'<div class="error" role="alert"><strong>本次调用未成功</strong><p>{_escape(error)}</p></div>'
    answer_text = call.answer
    if is_jev:
        answers = data.get("answers")
        category = answers.get("category") if isinstance(answers, dict) else None
        if isinstance(category, dict) and isinstance(category.get("choice"), str):
            answer_text = f"choice → {category['choice']}\n\n{answer_text}"
    answer = (
        f'<section class="answer"><h3>{"分类结果解读" if is_jev else "提取后的回答"}</h3>'
        f'<pre>{_escape(answer_text) if answer_text else "未提供可展示的答案；请查看状态与返回结构。"}</pre></section>'
    )
    returned = '<p class="muted missing">无返回 JSON；请求参数仍可展开查看。</p>'
    if response is not None:
        safe_json = json.dumps(mask_opaque_state(response), ensure_ascii=False, indent=2)
        returned = _json_panel("02 / 返回结构", response)
        returned += (
            '<details class="raw"><summary>展开完整 API 返回 JSON</summary>'
            '<p class="muted">保留全部字段；encrypted_content 的值已遮蔽。</p>'
            f'<pre>{_escape(safe_json)}</pre></details>'
        )
    return (
        f'<article class="provider {"jev" if is_jev else "openai"}" aria-labelledby="provider-{index}">'
        f'<header class="provider-head"><span class="eyebrow">API / {index + 1:02d}</span>'
        f'<h2 id="provider-{index}">{_escape(call.provider)}</h2>'
        f'<span class="protocol">{_escape(call.protocol)}</span></header>'
        f'<p class="semantics">{semantics}</p><dl class="metrics">{metrics}</dl>'
        + notice + answer + (_probabilities(data) if is_jev else "")
        + _json_panel("01 / 请求结构", call.request) + returned + "</article>"
    )


STYLE = """
:root{color-scheme:dark;font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;background:#0b1120;color:#e8edf8}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 10% 0%,#222657 0,transparent 46%),#0b1120}
main{max-width:1560px;margin:auto;padding:48px 28px 32px}h1,h2,h3,p{margin-top:0}
.eyebrow{font-size:11px;letter-spacing:.18em;font-weight:750;color:#a5b4fc}
h1{font-size:clamp(30px,4.5vw,58px);letter-spacing:-.05em;margin:14px 0;line-height:1.12}
.intro{max-width:780px;color:#b6c3d9;line-height:1.9}.shared{background:#151e33;border:1px solid #344267;border-radius:18px;padding:24px;margin:28px 0}
.shared h2{font-size:13px;color:#99adcf}.shared pre{font-size:17px;line-height:1.85}
pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:14px/1.8 ui-monospace,Consolas,monospace}
.columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;align-items:start}
.provider{min-width:0;background:#111b2e;border:1px solid #303e59;border-top:3px solid #9a9dff;border-radius:18px;padding:26px}
.provider.jev{border-top-color:#48d6c0}.provider-head h2{font-size:30px;margin:9px 0 10px;overflow-wrap:anywhere}
.jev .eyebrow{color:#72dece}.protocol{display:inline-block;font-size:12px;color:#ccd5ee;background:#25314c;border-radius:6px;padding:5px 9px}
.semantics{font-size:13px;color:#b6c3d9;line-height:1.9;margin:20px 0}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 22px}
.metric{padding:13px 10px;background:#1a2640;border:1px solid #2b3955;border-radius:10px;min-width:0}
dt{font-size:11px;color:#a5b5d0}dd{font-size:15px;font-weight:650;margin:7px 0 0;overflow-wrap:anywhere}
h3{font-size:14px;letter-spacing:.02em;margin-bottom:13px}.answer{border-left:3px solid #969bff;padding:6px 0 6px 16px;margin:25px 0}
.jev .answer{border-color:#48d6c0}.answer pre{font-family:inherit;color:#e0e8f7;font-size:15px}
.json-panel{border-top:1px solid #303e59;padding-top:22px;margin-top:24px}.tree-help,.muted{font-size:12px;color:#a6b6d0;line-height:1.8}
.tree-help{margin-bottom:14px}.tree,.children{list-style:none;margin:0;padding:0}
.tree{font:12px/1.8 ui-monospace,Consolas,monospace;overflow-x:auto;padding-bottom:6px}
.children{border-left:1px solid #42516d;margin-left:7px;padding-left:16px}
.children>li{position:relative}.children>li:before{position:absolute;left:-16px;top:13px;width:11px;border-top:1px solid #42516d;content:""}
summary{cursor:pointer;padding:4px 0;overflow-wrap:anywhere}summary:focus-visible{outline:2px solid #75dfd1;outline-offset:3px}
.leaf{padding:4px 0;overflow-wrap:anywhere}.key{font-weight:700;color:#d2dafe}.colon{color:#8091ae;margin:0 7px}
.badge{font:10px/1.5 "Segoe UI",sans-serif;display:inline-block;vertical-align:middle;border:1px solid #43516a;border-radius:4px;color:#bbcae1;padding:0 5px;margin-left:7px}
.hint{display:block;color:#a2b3d0;font:11px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;margin:2px 0 3px}
.string{color:#81ddc7;white-space:pre-wrap}.number{color:#fdcf8a}.boolean{color:#bbacff}.null,.empty{color:#9eacc3}
.raw{margin-top:20px;border:1px solid #33435d;border-radius:10px;padding:12px}.raw summary{font-size:12px;color:#aebfdb}
.raw pre{font-size:11px;padding-top:8px;max-height:520px;overflow:auto}.error{background:#381d2b;border:1px solid #b75970;padding:16px;border-radius:10px;color:#ffb9c5;margin:20px 0}
.error p{white-space:pre-wrap;overflow-wrap:anywhere;margin:9px 0 0;font-size:13px}.distribution{background:#122c32;border:1px solid #28545c;padding:18px;border-radius:12px}
.probability{margin-top:14px}.bar-label{display:flex;justify-content:space-between;gap:12px;font-size:12px;overflow-wrap:anywhere}
.bar{height:9px;background:#29424a;border-radius:10px;margin-top:8px;overflow:hidden}.bar>span{display:block;height:100%;background:#51d5be;border-radius:10px}
.confidence{font-size:12px;line-height:1.8;color:#b4e4da;margin:18px 0 0}.missing{padding:20px 0}
footer{border-top:1px solid #33415b;margin-top:32px;padding-top:20px;color:#a4b4ce;font-size:12px;line-height:1.9}
@media(max-width:880px){.columns{grid-template-columns:1fr}main{padding:28px 16px}.provider{padding:20px}}
@media(max-width:420px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.provider{padding:16px}.children{padding-left:12px}}
"""


def write_dashboard(path: Path, prompt: str, calls: list[CallResult]) -> None:
    columns = "".join(_provider(call, index) for index, call in enumerate(calls))
    if not calls:
        columns = '<p class="error">尚无调用记录，不能据此判断服务是否成功。</p>'
    page = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; script-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        f'<title>Demo 1 · 两种 API，一次看懂</title><style>{STYLE}</style></head><body><main>'
        '<header><span class="eyebrow">AI QUICK LEARN / REQUEST → RESPONSE</span>'
        '<h1>两种 API，一次看懂。</h1>'
        '<p class="intro">左看语言模型的文本生成，右看 TypeSafe 的结构化判断。'
        '从共同输入出发，沿着请求、结果解读和 JSON 树，理解每个字段的角色。</p></header>'
        '<section class="shared"><h2>SHARED INPUT / 本次共同输入</h2>'
        f'<pre>{_escape(prompt)}</pre></section><div class="columns">{columns}</div>'
        '<footer>读图提示：两种 API 的任务与返回语义不同；本次耗时只是单次运行记录，'
        '不是性能基准，也不能据此认定任何服务普遍更优。用量缺失不会补成 0，'
        '未识别字段仍保留在 JSON 树。<br>'
        '本页为离线只读 HTML，无 JavaScript、远程资源或网络请求。'
        '加密推理字段已遮蔽，但输入、答案和其他返回字段可能含私人信息，分享前请检查。</footer>'
        '</main></body></html>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def write_report(path: Path, model: str, prompt: str, response: Response) -> None:
    """兼容单次 Responses 调用；仅重建已知请求字段，不猜测未记录的选项。"""
    request: dict[str, object] = {"model": model, "input": prompt}
    instructions = getattr(response, "instructions", None)
    if instructions is not None:
        request["instructions"] = instructions
    write_dashboard(path, prompt, [CallResult(
        provider="OpenAI", protocol="Responses API", request=request,
        response=response.model_dump(mode="json"), answer=response.output_text,
    )])
