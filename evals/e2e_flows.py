"""Real end-to-end flows against a running stack (docker compose), saved as evidence.

    docker compose up -d
    uv run python -m evals.e2e_flows --merchant-token "$T" --operator-token "$O"

Flows: (1) multi-turn memory with a follow-up reference, (2) human handoff for a disputed
charge: escalation -> signed operator webhook -> operator reply -> supervisor resumes ->
merchant notified (SSE + webhook). Writes evals/results/<ts>-e2e-flows/transcript.json.
"""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--merchant-token", required=True)
    parser.add_argument("--operator-token", required=True)
    args = parser.parse_args()
    client = httpx.Client(base_url=args.url, timeout=240)
    merchant = {"Authorization": f"Bearer {args.merchant_token}"}
    operator = {"Authorization": f"Bearer {args.operator_token}"}
    log: list[dict[str, Any]] = []

    def chat(message: str, session: str) -> dict[str, Any]:
        body = client.post(
            "/chat",
            headers=merchant,
            json={"message": message, "user_id": "cliente1988", "session_id": session},
        ).json()
        log.append({"step": "merchant", "session": session, "message": message, "response": body})
        print(
            f"[{session}] {message!r} -> {body.get('outcome')} agents={body.get('agents_used')}",
            flush=True,
        )
        return dict(body)

    memory = f"mem-{uuid.uuid4().hex[:6]}"
    chat("Quanto eu vendi ontem no total?", memory)
    chat("E no dia anterior a esse?", memory)

    handoff_session = f"hitl-{uuid.uuid4().hex[:6]}"
    first = chat(
        "Meu cliente foi cobrado duas vezes ontem no mesmo cartão, no valor de "
        "R$ 239,90. Quero que estornem uma das vendas.",
        handoff_session,
    )
    handoff = (first.get("handoff") or {}).get("id")
    if handoff:
        queue = client.get("/operator/handoffs", headers=operator).json()
        log.append({"step": "operator_queue", "response": queue})
        reply = client.post(
            f"/operator/handoffs/{handoff}/reply",
            headers=operator,
            json={
                "action": "instruct",
                "message": "Confirmei a duplicidade. O estorno da segunda venda foi solicitado ao "
                "time de cancelamentos. Explique ao lojista que o valor volta para a "
                "fatura do cliente conforme o prazo do emissor e informe o protocolo.",
            },
        ).json()
        log.append({"step": "operator_reply", "handoff": handoff, "response": reply})
        print(f"operator reply -> {reply.get('outcome')}", flush=True)
        events = client.get(f"/sessions/{handoff_session}/events?wait_s=2", headers=merchant).text
        log.append({"step": "merchant_sse", "events": events})

    out = ROOT / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-e2e-flows"
    out.mkdir(parents=True, exist_ok=True)
    (out / "transcript.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), "utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
