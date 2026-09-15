"""Manual smoke test for the Ollama client. Run: python smoke_ollama.py"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ollama_client import (  # noqa: E402
    ChatMessage,
    ModelNotFound,
    OllamaClient,
    OllamaUnavailable,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> int:
    client = OllamaClient(model="qwen3:1.7b")
    print(f"host={client.host} model={client.model}")

    print("\n[1] availability")
    if not client.is_available():
        print("  FAIL: Ollama server not reachable")
        return 1
    print(f"  OK version={client.version()}")

    print("\n[2] installed models")
    models = client.list_models()
    for m in models:
        print(f"  {m}")
    if not client.has_model():
        print(f"  FAIL: configured model {client.model!r} not installed")
        return 1
    print(f"  OK {client.model!r} present; supports_tools={client.supports_tools()}")

    print("\n[3] plain chat")
    t0 = time.time()
    resp = client.chat(
        [ChatMessage.system("You are terse. One short sentence only."),
         ChatMessage.user("Say the word READY.")]
    )
    dt = time.time() - t0
    print(f"  content={resp.message.content!r}")
    print(f"  {dt:.1f}s  eval={resp.eval_count} tok  load={resp.load_duration_ns/1e9:.1f}s")
    if not resp.message.content.strip():
        print("  FAIL: empty response")
        return 1
    print("  OK")

    print("\n[4] streaming")
    got: list[str] = []
    t0 = time.time()
    first_at = [None]

    def on_token(tok: str) -> None:
        if first_at[0] is None:
            first_at[0] = time.time() - t0
        got.append(tok)

    resp = client.chat_stream(
        [ChatMessage.system("You are terse. One short sentence only."),
         ChatMessage.user("Count from 1 to 5 in words only.")],
        on_token=on_token,
    )
    print(f"  text={''.join(got)!r}")
    print(f"  first_token={first_at[0]:.2f}s total={time.time()-t0:.1f}s")
    if not got:
        print("  FAIL: no streamed tokens")
        return 1
    print("  OK")

    print("\n[5] native tool calling")
    tools = [{
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Launch an application by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "app name"}},
                "required": ["name"],
            },
        },
    }]
    resp = client.chat(
        [ChatMessage.system("Use tools when asked. Do not explain."),
         ChatMessage.user("Open Notepad.")],
        tools=tools,
    )
    if not resp.message.tool_calls:
        print(f"  FAIL: no tool call. content={resp.message.content!r}")
        return 1
    tc = resp.message.tool_calls[0]
    print(f"  OK {tc.name}({tc.arguments})")

    print("\n[6] model-not-found error message")
    bad = OllamaClient(model="does-not-exist:99b")
    try:
        bad.ensure_ready()
        print("  FAIL: expected ModelNotFound")
        return 1
    except ModelNotFound as exc:
        print("  OK raised ModelNotFound:")
        for line in str(exc).splitlines():
            print(f"    {line}")

    print("\n[7] unreachable-host error message")
    dead = OllamaClient(host="http://127.0.0.1:59999", timeout=3, max_retries=0)
    try:
        dead.chat([ChatMessage.user("hi")])
        print("  FAIL: expected OllamaUnavailable")
        return 1
    except OllamaUnavailable as exc:
        print("  OK raised OllamaUnavailable:")
        for line in str(exc).splitlines():
            print(f"    {line}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: wrong error type {type(exc).__name__}: {exc}")
        return 1

    print("\nALL OLLAMA CLIENT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
