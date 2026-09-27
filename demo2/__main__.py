"""第二课：把历史传回模型，观察多轮对话的短期记忆。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from openai import OpenAI
from openai.types.responses import ResponseInputItemParam
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming

from demo_support import create_client, ensure_completed, run_cli
from demo_visualizer import Trace

DEFAULT_PROMPTS = [
    "请记住这个虚构练习代号：海星42。我每天可以学习20分钟，目标是学会 Python Agent。请简短确认。",
    "我的练习代号是什么？每天可以学多久？",
    "结合前面说的目标和时间，给我一个两天学习计划。",
]


def chat_turn(
    client: OpenAI, model: str, history: list[ResponseInputItemParam], prompt: str,
    trace: Trace | None = None, step: int = 1,
) -> str:
    trace = trace if trace is not None else Trace(2, model)
    user_message: ResponseInputItemParam = {"role": "user", "content": prompt}
    print(f"\n用户：{prompt}\n本次携带 {len(history)} 个历史项，再追加这一条用户消息。")
    trace.add("user", "用户提出新问题", step, text=prompt, history_items=len(history))
    request: ResponseCreateParamsNonStreaming = {
        "model": model,
        "instructions": "你是中文编程助教。根据提供的对话历史回答，不编造未提供的个人信息。",
        "input": [*history, user_message],
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "max_output_tokens": 2048,
    }
    with trace.model_request(step, request) as returned:
        response = client.responses.create(**request)
        returned(response)
    ensure_completed(response)
    if not response.output_text.strip():
        raise RuntimeError("模型没有返回文本；这一轮不写入对话历史。")
    before = len(history)
    history.append(user_message)
    # 保存完整输出，包括推理模型的加密上下文；不要只保存 output_text。
    history.extend(
        cast(ResponseInputItemParam, item.model_dump(mode="json", exclude_none=True))
        for item in response.output
    )
    trace.add("memory", "保存本轮完整历史", step, before=before, after=len(history), history=history)
    trace.add("answer", "助手回答", step, text=response.output_text)
    print(f"助手：{response.output_text}")
    return response.output_text


def run_conversation(
    client: OpenAI, model: str, prompts: list[str], trace: Trace | None = None,
) -> list[str]:
    if not 1 <= len(prompts) <= 20:
        raise ValueError("一次演示需要 1 到 20 条用户消息。")
    history: list[ResponseInputItemParam] = []
    return [
        chat_turn(client, model, history, prompt, trace, step)
        for step, prompt in enumerate(prompts, 1)
    ]


def interactive_chat(
    client: OpenAI, model: str, max_turns: int, trace: Trace | None = None,
) -> None:
    trace = trace if trace is not None else Trace(2, model)
    history: list[ResponseInputItemParam] = []
    print("输入消息开始对话；/reset 清空记忆，/exit 退出。历史只保存在当前进程。")
    turns = 0
    while turns < max_turns:
        try:
            prompt = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n对话结束。")
            return
        if prompt == "/exit":
            return
        if prompt == "/reset":
            before = len(history)
            history.clear()
            trace.add("reset", "清空对话记忆", turns, before=before, after=0, history=[])
            print("已清空对话历史；调用次数预算不重置。")
            continue
        if not prompt:
            continue
        chat_turn(client, model, history, prompt, trace, turns + 1)
        turns += 1
    print(f"已达到 {max_turns} 轮对话预算，停止请求。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompts", nargs="*", help="自定义多条用户消息，默认演示三轮记忆")
    parser.add_argument("--interactive", action="store_true", help="交互式对话")
    parser.add_argument("--max-turns", type=int, default=6, choices=range(1, 21))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("result.html"),
                        help="可视化 HTML 路径，每一步自动更新；浏览器刷新查看")
    args = parser.parse_args()
    if args.interactive and args.prompts:
        parser.error("--interactive 不能同时提供预设消息。")
    prompts = args.prompts or DEFAULT_PROMPTS
    if not args.interactive and len(prompts) > args.max_turns:
        parser.error("预设消息数量超过 --max-turns；请增加预算或减少消息。")
    print(f"可视化结果：{args.output.resolve()}")
    with Trace(2, path=args.output) as trace:
        client, model = create_client()
        trace.model = model
        with client:
            if args.interactive:
                interactive_chat(client, model, args.max_turns, trace)
            else:
                run_conversation(client, model, prompts, trace)


if __name__ == "__main__":
    run_cli(main)
