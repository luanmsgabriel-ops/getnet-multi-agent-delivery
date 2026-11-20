"""Does a saved communication preference change the answer? (v3 gap: saved but ignored)

    uv run python -m evals.style_preference --label before

The same questions are asked by the same merchant twice, on fresh data: once with no saved
memory and once with `communication_preference` set to short answers. The report compares
answer length (characters and lines) per question. Real model; about US$ 0.15 per run.
"""

import argparse
import json
import statistics
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PREFERENCE = "Prefere respostas curtas e diretas: no máximo 3 linhas, sem tabelas."
QUESTIONS = (
    "Qual a diferença entre a Get Smart e a Get Clássica?",
    "Quanto eu vendi ontem?",
    "Como eu habilito o Pix na maquininha?",
)


def run(preference: str | None) -> list[dict[str, Any]]:
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.data.db import Database
    from app.main import create_app
    from app.memory import MemoryStore
    from app.security.auth import issue_token

    out = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = get_settings().model_copy(
            update={"data_dir": Path(tmp), "oidc_issuer": None, "expose_tool_results": False}
        )
        if preference:
            state = Database(settings.db_path)
            state.init()
            MemoryStore(state).put("demo", "cliente1988", "communication_preference", preference)
        with TestClient(create_app(settings)) as client:
            headers = {"Authorization": f"Bearer {issue_token(settings, 'cliente1988')[0]}"}
            for q in QUESTIONS:
                body = client.post(
                    "/chat",
                    headers=headers,
                    json={"message": q, "user_id": "cliente1988", "session_id": uuid.uuid4().hex},
                ).json()
                answer = str(body.get("answer", ""))
                out.append(
                    {
                        "question": q,
                        "preference": bool(preference),
                        "outcome": body.get("outcome"),
                        "chars": len(answer),
                        "lines": len([x for x in answer.splitlines() if x.strip()]),
                        "has_table": "|---" in answer,
                        "answer": answer,
                        "cost_usd": (body.get("usage") or {}).get("cost_usd"),
                    }
                )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    opts = parser.parse_args()
    rows = run(None) + run(PREFERENCE)
    base = {r["question"]: r for r in rows if not r["preference"]}
    pref = {r["question"]: r for r in rows if r["preference"]}
    ratios = [pref[q]["chars"] / max(1, base[q]["chars"]) for q in QUESTIONS]
    lines = [
        f"# Saved communication preference ({opts.label or 'run'})",
        "",
        f'Preference saved for the merchant: "{PREFERENCE}"',
        "",
        "| Question | Chars without / with | Lines without / with | Table with preference |",
        "|---|---|---|---|",
        *(
            f"| {q} | {base[q]['chars']} / {pref[q]['chars']} | {base[q]['lines']} / "
            f"{pref[q]['lines']} | {pref[q]['has_table']} |"
            for q in QUESTIONS
        ),
        "",
        f"Median length with the preference: **{statistics.median(ratios):.0%}** of the answer "
        "without it. Cost: US$ "
        f"{sum(float(r['cost_usd'] or 0) for r in rows):.3f}.",
        "",
        "## Answers with the preference",
        "",
        *(f"**{q}**\n\n> " + pref[q]["answer"].replace("\n", "\n> ") + "\n" for q in QUESTIONS),
    ]
    out = (
        ROOT
        / "results"
        / (
            f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-style-preference"
            + (f"-{opts.label}" if opts.label else "")
        )
    )
    out.mkdir(parents=True)
    (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
    (out / "raw.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
    )
    print("\n".join(lines[:12]).encode("ascii", "replace").decode())
    print(f"saved {out}")


if __name__ == "__main__":
    main()
