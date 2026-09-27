"""三个 demo 共用的认证和错误显示；Agent 循环留在各课中。"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AzureCliCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError
from openai.types.responses import Response


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def create_client() -> tuple[OpenAI, str]:
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not model:
        raise ValueError("请设置 OPENAI_MODEL；Azure 下填写部署名，而不是资源名。")
    auth = os.environ.get("OPENAI_AUTH", "api-key").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/").strip()
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
    ):
        raise ValueError("OPENAI_BASE_URL 必须是不含凭据、查询参数或片段的 HTTPS API 地址。")
    if auth == "azure-cli":
        azure_domains = (".openai.azure.com", ".cognitiveservices.azure.com", ".services.ai.azure.com")
        if not parsed.hostname.endswith(azure_domains) or parsed.path.rstrip("/") != "/openai/v1":
            raise ValueError("azure-cli 模式需要 Azure 官方域名下的 /openai/v1/ 地址。")
        token_provider = get_bearer_token_provider(
            AzureCliCredential(),
            os.environ.get("AZURE_TOKEN_SCOPE", "https://ai.azure.com/.default"),
        )
        client = OpenAI(
            base_url=base_url, api_key=token_provider, timeout=60.0, max_retries=0
        )
    elif auth == "api-key":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("api-key 模式需要 OPENAI_API_KEY，或改用 OPENAI_AUTH=azure-cli。")
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0, max_retries=0)
    else:
        raise ValueError("OPENAI_AUTH 只支持 api-key 或 azure-cli。")
    return client, model


def ensure_completed(response: Response) -> None:
    if response.status != "completed":
        reason = response.incomplete_details.reason if response.incomplete_details else response.status
        raise RuntimeError(f"模型未完整返回（{reason}）；不执行不完整的工具请求。")


def run_cli(main: Callable[[], None]) -> None:
    configure_console()
    try:
        main()
    except ClientAuthenticationError:
        print("认证失败：请运行 az login，并确认账号拥有模型的数据面调用权限。", file=sys.stderr)
        raise SystemExit(1)
    except APIStatusError as exc:
        print(
            f"API 请求失败：HTTP {exc.status_code}，request_id={exc.request_id}。"
            "请检查端点、部署名、权限、配额及 Responses 支持情况。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except APIConnectionError:
        print("API 连接失败或超时：请检查网络、代理和端点。", file=sys.stderr)
        raise SystemExit(1)
    except OpenAIError:
        print("OpenAI SDK 请求失败；请检查依赖版本与 API 配置。", file=sys.stderr)
        raise SystemExit(1)
    except OSError:
        print("本地文件读写失败：请检查输出路径和文件权限。", file=sys.stderr)
        raise SystemExit(1)
    except (ValueError, RuntimeError) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
