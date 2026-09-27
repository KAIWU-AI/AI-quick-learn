"""第一课：分别请求大语言模型和 JEV，观察两种 API 的输入与完整返回。"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from collections.abc import Callable

from azure.core.exceptions import ClientAuthenticationError
from dotenv import load_dotenv
from openai import APIStatusError, OpenAI, OpenAIError
from openai.types.responses import Response

from demo_support import create_client, ensure_completed, run_cli
from demo1.jev import DEFAULT_PROMPT, make_request, request_jev
from demo1.report import CallResult, mask_opaque_state, write_dashboard

INSTRUCTIONS = (
    "你是一名中文客服助教。请将工单归为 billing（支付、扣款、发票、退款）、"
    "technical（软件缺陷或技术故障）或 other（其他），并简短说明理由。"
)


def make_llm_request(model: str, prompt: str) -> dict[str, object]:
    return {
        "model": model, "instructions": INSTRUCTIONS, "input": prompt,
        "store": False, "max_output_tokens": 2048,
    }


def run(client: OpenAI, model: str, prompt: str) -> Response:
    print("=== 输入 ===")
    print(json.dumps(make_llm_request(model, prompt), ensure_ascii=False, indent=2))
    response = client.responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=prompt,
        store=False,
        max_output_tokens=2048,
    )
    print("=== 完整 API 返回 ===")
    print(json.dumps(mask_opaque_state(response.model_dump(mode="json")), ensure_ascii=False, indent=2))
    ensure_completed(response)
    if not response.output_text.strip():
        raise RuntimeError("模型没有返回文本；请检查完整返回中的拒绝信息或其他输出项。")
    print("=== 提取后的 output_text ===")
    print(response.output_text)
    return response


def call_llm(prompt: str) -> tuple[dict[str, object], str]:
    client, model = create_client()
    with client:
        response = run(client, model, prompt)
    return response.model_dump(mode="json"), response.output_text


def call_jev(payload: dict[str, object]) -> tuple[dict[str, object], str]:
    print("=== JEV 请求正文（不含认证头） ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    result = request_jev(payload)
    print("=== JEV 完整返回 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result, "JEV 返回类型化分类；请查看下方 choice、confidence 和 probabilities 的解读。"


def collect_result(
    provider: str, protocol: str, payload: dict[str, object],
    invoke: Callable[[], tuple[dict[str, object], str]],
) -> CallResult:
    started = time.perf_counter()
    result = CallResult(provider=provider, protocol=protocol, request=payload)
    try:
        result.response, result.answer = invoke()
    except (OpenAIError, ClientAuthenticationError, ValueError, RuntimeError, OSError) as exc:
        if isinstance(exc, APIStatusError):
            result.error = f"请求失败：HTTP {exc.status_code}。请检查模型、端点、权限和额度。"
        elif isinstance(exc, (ValueError, RuntimeError)):
            result.error = str(exc)
        else:
            result.error = f"请求未完成（{type(exc).__name__}）；请检查认证、网络和本地配置。"
        print(f"{provider} 失败：{result.error}")
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("result.html"),
        help="可视化 HTML 输出路径；重复运行会更新该文件",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    llm_payload = make_llm_request(os.environ.get("OPENAI_MODEL", "未配置"), args.prompt)
    jev_payload = make_request(args.prompt, os.environ.get("JEV_MODEL", "jev-latest"))
    results = [
        collect_result("OpenAI", "Responses API", llm_payload, lambda: call_llm(args.prompt)),
        collect_result("JEV", "TypeSafe systemone", jev_payload, lambda: call_jev(jev_payload)),
    ]
    write_dashboard(args.output, args.prompt, results)
    print(f"\n可视化结果：{args.output.resolve()}")
    if any(result.error for result in results):
        raise RuntimeError("部分接口调用失败；报告已保留成功结果并明确标出错误。")


if __name__ == "__main__":
    run_cli(main)
