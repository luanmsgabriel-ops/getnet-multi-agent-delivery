"""Real-model check of long-chat summary and long-term merchant memory (in-process).

    uv run python -m evals.memory_flow

1. The merchant states lasting facts while asking something else; the supervisor should save
   them with `remember`, and GET /me/memory should list them (redacted).
2. A long chat: a protocol number in the first message must still be recalled after the
   oldest turns were folded into the summary.
3. DELETE /me/memory erases everything.
Writes evals/results/<ts>-memory-flow/transcript.json and prints pass/fail per check.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FILLERS = [
    "Ok, entendi.",
    "Certo, obrigado.",
    "E o que mais eu preciso saber sobre isso?",
    "Beleza.",
    "Entendi, vou verificar a conexão.",
    "Ok.",
    "Perfeito, obrigado pela ajuda.",
    "Certo.",
]


def main() -> None:
    os.environ["EXPOSE_TOOL_RESULTS"] = "1"
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app
    from app.security.auth import issue_token

    settings = get_settings()
    log: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    with TestClient(create_app(settings)) as c:
        headers = {"Authorization": f"Bearer {issue_token(settings, 'cliente1988')[0]}"}
        c.delete("/me/memory", headers=headers)

        def chat(message: str, session: str) -> dict[str, Any]:
            body: dict[str, Any] = c.post(
                "/chat",
                headers=headers,
                json={"message": message, "user_id": "cliente1988", "session_id": session},
            ).json()
            log.append({"session": session, "message": message, "response": body})
            print(f"[{session}] {message[:50]!r} -> {body.get('outcome')}", flush=True)
            return body

        first = chat(
            "Tenho uma padaria com duas lojas e prefiro respostas curtas. "
            "Quanto eu vendi ontem no total?",
            f"facts-{uuid.uuid4().hex[:6]}",
        )
        tools = {f"{t['agent']}.{t['tool']}" for t in first.get("tool_calls", [])}
        checks["remember called while answering the question"] = "supervisor.remember" in tools
        checks["question still answered with merchant data"] = "support" in first.get(
            "agents_used", []
        )
        saved = c.get("/me/memory", headers=headers).json()
        log.append({"step": "GET /me/memory", "response": saved})
        checks["memory lists the business profile"] = "padaria" in json.dumps(saved).lower()

        later = chat(
            "Como posso receber minhas vendas mais rápido?", f"later-{uuid.uuid4().hex[:6]}"
        )
        checks["new session answered"] = later.get("outcome") == "answered"

        long_session = f"long-{uuid.uuid4().hex[:6]}"
        chat(
            "Minha maquininha está offline desde ontem. Num atendimento anterior me passaram o "
            "protocolo HD-7731.",
            long_session,
        )
        for message in FILLERS:
            chat(message, long_session)
        recall = chat("Qual era o número do protocolo que eu mencionei no começo?", long_session)
        checks["protocol recalled after summarization"] = "HD-7731" in recall.get("answer", "")

        c.delete("/me/memory", headers=headers)
        checks["memory erased"] = c.get("/me/memory", headers=headers).json() == {}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / f"{stamp}-memory-flow"
    out.mkdir(parents=True, exist_ok=True)
    cost = sum(e["response"].get("usage", {}).get("cost_usd", 0) for e in log if "message" in e)
    (out / "transcript.json").write_text(
        json.dumps(
            {"checks": checks, "cost_usd": round(cost, 4), "log": log}, ensure_ascii=False, indent=2
        ),
        "utf-8",
    )
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"cost US$ {cost:.4f}; wrote {out}")


if __name__ == "__main__":
    main()
