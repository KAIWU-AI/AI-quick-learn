"""第三课：在对话历史上加入工具执行与反馈，构建首个多工具代理循环。"""

import argparse
import json
import time
from pathlib import Path
from typing import cast

from openai import OpenAI
from openai.types.responses import FunctionToolParam, ResponseInputItemParam
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming

from demo_support import create_client, ensure_completed, run_cli
from demo_visualizer import Trace

CATALOG = {
    "api": {"title": "Responses API 入门", "minutes": 20, "prerequisites": []},
    "memory": {"title": "多轮对话记忆", "minutes": 30, "prerequisites": ["api"]},
    "tools": {"title": "多工具 Agent Loop", "minutes": 40, "prerequisites": ["memory"]},
}

TOOLS: list[FunctionToolParam] = [
    {
        "type": "function",
        "name": "list_courses",
        "description": "列出虚构课程目录，只返回课程 ID 和标题，不含时长。",
        "parameters": {
            "type": "object", "properties": {}, "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_course",
        "description": "按课程 ID 查询标题、分钟数和先修课程 ID。",
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "string", "enum": ["api", "memory", "tools"]}},
            "required": ["course_id"], "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "sum_minutes",
        "description": "将查询得到的课程分钟数相加，返回 total_minutes。",
        "parameters": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 480},
                    "minItems": 1, "maxItems": 10,
                }
            },
            "required": ["minutes"], "additionalProperties": False,
        },
        "strict": True,
    },
]

DEFAULT_PROMPT = (
    "请先调用 list_courses 列出课程，再用 get_course 查询全部三门课程，"
    "最后必须调用 sum_minutes 计算总时长。"
    "根据先修关系，用中文给出学习顺序与总分钟数。"
)
INSTRUCTIONS = (
    "你是课程学习助手。目录是虚构教学数据，只能通过提供的工具获取课程事实。"
    "需要时长时先查询详情，求总时长时使用 sum_minutes，不要自行猜测。"
    "工具返回 error 时检查并修正参数；不要把错误当作成功结果。用中文回答。"
)


def dispatch_tool(name: str, arguments: str) -> str:
    """白名单分派；即使启用了 strict，也在本地验证模型传来的数据。"""
    result: object
    try:
        args = json.loads(arguments)
        if not isinstance(args, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        if name == "list_courses":
            if args:
                raise ValueError("list_courses 不接受任何参数")
            result = [
                {"course_id": course_id, "title": course["title"]}
                for course_id, course in CATALOG.items()
            ]
        elif name == "get_course":
            if set(args) != {"course_id"}:
                raise ValueError("get_course 只接受必填参数 course_id")
            course_id = args["course_id"]
            if not isinstance(course_id, str) or course_id not in CATALOG:
                raise ValueError("course_id 必须是 api、memory 或 tools")
            result = CATALOG[course_id]
        elif name == "sum_minutes":
            if set(args) != {"minutes"}:
                raise ValueError("sum_minutes 只接受必填参数 minutes")
            minutes = args["minutes"]
            if not isinstance(minutes, list) or not 1 <= len(minutes) <= 10:
                raise ValueError("minutes 必须是包含 1 到 10 项的数组")
            if any(type(value) is not int or not 0 <= value <= 480 for value in minutes):
                raise ValueError("每项分钟数必须是 0 到 480 的整数，不能是布尔值")
            result = {"total_minutes": sum(minutes)}
        else:
            raise ValueError(f"未知工具：{name}")
    except (ValueError, TypeError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


def run_agent(
    client: OpenAI, model: str, prompt: str, max_steps: int = 8, trace: Trace | None = None,
) -> str:
    if type(max_steps) is not int or not 1 <= max_steps <= 12:
        raise ValueError("max_steps 必须是 1 到 12 的整数")
    history: list[ResponseInputItemParam] = [{"role": "user", "content": prompt}]
    trace = trace if trace is not None else Trace(3, model)
    trace.add("user", "用户提交任务", text=prompt)
    for step in range(1, max_steps + 1):
        print(f"\n[请求轮次 {step}/{max_steps}]")
        request: ResponseCreateParamsNonStreaming = {
            "model": model, "instructions": INSTRUCTIONS, "input": history,
            "tools": TOOLS, "store": False, "include": ["reasoning.encrypted_content"],
            "max_output_tokens": 2048,
        }
        with trace.model_request(step, request) as returned:
            response = client.responses.create(**request)
            returned(response)
        ensure_completed(response)
        before = len(history)
        # 完整回传 output；reasoning 也是上下文，但不要把它打印出来。
        history.extend(
            cast(ResponseInputItemParam, item.model_dump(mode="json", exclude_none=True))
            for item in response.output
        )
        trace.add("memory", "保存模型完整输出", step, before=before, after=len(history), history=history)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if not response.output_text.strip():
                raise RuntimeError("模型既未调用工具，也未返回非空文本")
            print(f"\n[最终回答]\n{response.output_text}")
            trace.add("final", "获得最终回答，退出 Loop", step, text=response.output_text)
            return response.output_text
        # 一轮可以请求多个工具；本地顺序执行，全部结果追加后才发下一轮。
        for call in calls:
            print(f"[工具调用] {call.name} {call.arguments}")
            trace.add("tool_call", f"调用 {call.name}", step,
                      name=call.name, call_id=call.call_id, arguments=call.arguments)
            started = time.perf_counter()
            output = dispatch_tool(call.name, call.arguments)
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[工具结果] {output}")
            result = json.loads(output)
            trace.add("tool_result", f"{call.name} 返回结果", step,
                      elapsed_ms=elapsed_ms, error=isinstance(result, dict) and "error" in result,
                      name=call.name, call_id=call.call_id, output=result)
            before = len(history)
            history.append({
                "type": "function_call_output", "call_id": call.call_id, "output": output,
            })
            trace.add("memory", "追加工具反馈，供后续请求使用", step,
                      before=before, after=len(history), history=history, call_id=call.call_id)
    raise RuntimeError(f"已达到 {max_steps} 轮请求上限，尚未获得最终回答")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="可选的课程问题")
    parser.add_argument("--max-steps", type=int, default=8, choices=range(1, 13))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("result.html"),
                        help="可视化 HTML 路径，每一步自动更新；浏览器刷新查看")
    args = parser.parse_args()
    print(f"可视化结果：{args.output.resolve()}")
    with Trace(3, path=args.output) as trace:
        client, model = create_client()
        trace.model = model
        with client:
            run_agent(client, model, args.prompt, args.max_steps, trace)


if __name__ == "__main__":
    run_cli(main)
