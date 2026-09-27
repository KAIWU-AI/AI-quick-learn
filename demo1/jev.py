"""一次 JEV HTTP API 调用：state + questions → typed answers。"""

from __future__ import annotations

import argparse
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from demo1.credentials import read_windows_credential
from demo_support import run_cli

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_PROMPT = "我被重复扣款了，请帮我退款。"
CRITERIA = {
    "billing": "Payments, charges, invoices, or refunds",
    "technical": "Software bugs or technical malfunctions",
    "other": "Anything that is neither billing nor technical support",
}


def make_request(document: str, model: str) -> dict[str, object]:
    return {
        "model": model,
        "state": {"document": document},
        "questions": {
            "category": {
                "type": "choice",
                "instructions": "What is the customer support ticket in `document` about?",
                "criteria": CRITERIA,
            }
        },
    }


def get_api_key() -> str:
    auth = os.environ.get("JEV_AUTH", "api-key").strip()
    if auth == "windows-credential":
        target = os.environ.get("JEV_CREDENTIAL_TARGET", "TypeSafe/Jev/APIKey").strip()
        if not target:
            raise ValueError("JEV_CREDENTIAL_TARGET 不能为空。")
        key = read_windows_credential(target)
    elif auth == "api-key":
        key = os.environ.get("JEV_API_KEY", "").strip()
    else:
        raise ValueError("JEV_AUTH 只支持 api-key 或 windows-credential。")
    if not key or key.startswith("YOUR_"):
        raise ValueError("请在本地 .env 配置 JEV_API_KEY，或显式使用 Windows 凭据模式。")
    return key


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_jev(payload: dict[str, object]) -> dict[str, object]:
    key = get_api_key()
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise RuntimeError("JEV 返回超过教学示例的 1 MB 上限。")
        result = json.loads(body.decode("utf-8").replace(key, "[REDACTED]"))
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise RuntimeError(f"JEV 请求失败：HTTP {code}。请检查密钥、模型、额度及请求格式。") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("JEV 连接失败或超时，请检查网络。") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("JEV 返回不是有效的 UTF-8 JSON。") from None
    if not isinstance(result, dict):
        raise RuntimeError("JEV 返回必须是 JSON 对象。")
    answers = result.get("answers")
    category = answers.get("category") if isinstance(answers, dict) else None
    if (
        not isinstance(category, dict) or category.get("type") != "choice"
        or not isinstance(category.get("choice"), str) or category["choice"] not in CRITERIA
    ):
        raise RuntimeError("JEV 返回缺少有效的 category choice。")
    confidence = category.get("confidence")
    probabilities = category.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(CRITERIA):
        raise RuntimeError("JEV 返回的 probabilities 与候选分类不一致。")
    for value in [confidence, *probabilities.values()]:
        if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
            raise RuntimeError("JEV 返回的 confidence 或 probabilities 不在有效范围内。")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    payload = make_request(args.prompt, os.environ.get("JEV_MODEL", "jev-latest"))
    print("=== JEV 请求正文（不含认证头） ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("=== JEV 返回 ===")
    print(json.dumps(request_jev(payload), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_cli(main)
