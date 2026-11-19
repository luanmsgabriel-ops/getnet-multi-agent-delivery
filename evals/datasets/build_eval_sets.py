"""Builds the answer-level eval sets (dev, multi_turn, handoff, holdout_answers).

dev / multi_turn / handoff are written by us and may be used to tune prompts.
holdout_answers takes official FAQ questions with their official answers from the
Getnet site snapshot (not written by us) and is run once for the reported number.

Case schema:
  {"id", "split", "tags", "turns": [message, ...],
   "expected": {"agents": [...], "tools": [...], "outcome": "answered|clarify|handoff|blocked",
                "must_include": [[alternatives...], ...], "must_not_include": [...]},
   "reference": "official answer (holdout only)"}
Expectations apply to the LAST turn. Agents/tools are "must have been used"; outcome is exact.
"""

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def case(
    cid: str,
    turns: str | list[str],
    agents: list[str] | None = None,
    tools: list[str] | None = None,
    outcome: str = "answered",
    include: list[list[str]] | None = None,
    exclude: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": cid,
        "tags": tags or [],
        "turns": [turns] if isinstance(turns, str) else turns,
        "expected": {
            "agents": agents or [],
            "tools": tools or [],
            "outcome": outcome,
            "must_include": include or [],
            "must_not_include": exclude or [],
        },
    }


K, S = ["knowledge"], ["support"]
DEV = [
    # Getnet knowledge, Portuguese
    case(
        "D01",
        "Qual a diferença entre a Get Smart e a Get Clássica?",
        K,
        ["search_kb"],
        include=[["Smart"], ["Clássica", "Classica"]],
        tags=["kb", "comparison"],
    ),
    case(
        "D02", "Como habilito o Pix pelo Portal?", K, ["search_kb"], include=[["Pix"]], tags=["kb"]
    ),
    case(
        "D03",
        "O que significa o erro ADQ 1-19 na maquininha?",
        K,
        ["search_kb"],
        include=[["1-19"]],
        tags=["kb", "error_code"],
    ),
    case(
        "D04",
        "Como configuro o Wi-Fi da minha maquininha?",
        K,
        ["search_kb"],
        include=[["Wi-Fi", "wifi", "WiFi"]],
        tags=["kb"],
    ),
    case(
        "D05",
        "Quando vale a pena antecipar as vendas no cartão?",
        K,
        ["search_kb"],
        include=[["antecip"]],
        tags=["kb"],
    ),
    case(
        "D06",
        "Ainda dá para receber pagamentos dentro do WhatsApp?",
        K,
        ["search_kb"],
        include=[["WhatsApp"]],
        tags=["kb"],
    ),
    case(
        "D07",
        "O que é o Conversor de Moedas (DCC) da Getnet?",
        K,
        ["search_kb"],
        include=[["moeda", "DCC"]],
        tags=["kb"],
    ),
    case("D08", "Como funciona o Get Tap?", K, ["search_kb"], include=[["Tap"]], tags=["kb"]),
    case(
        "D09",
        "Quais são os status possíveis de uma venda?",
        K,
        ["search_kb"],
        include=[["status"]],
        tags=["kb"],
    ),
    case(
        "D10",
        "Como cancelo uma venda que fiz hoje na maquininha?",
        K,
        ["search_kb"],
        include=[["cancel"]],
        tags=["kb"],
    ),
    # Getnet knowledge, English (cross-lingual retrieval)
    case(
        "D11",
        "How do I enable Pix sales in the Getnet portal?",
        K,
        ["search_kb"],
        include=[["Pix"]],
        tags=["kb", "en"],
    ),
    case(
        "D12",
        "How does a chargeback work at Getnet?",
        K,
        ["search_kb"],
        include=[["chargeback"]],
        tags=["kb", "en"],
    ),
    case(
        "D13",
        "Does the Get Smart print receipts?",
        K,
        ["search_kb"],
        include=[["receipt", "print"]],
        tags=["kb", "en"],
    ),
    case(
        "D14",
        "How can I sell online if I don't have a website?",
        K,
        ["search_kb"],
        include=[["link"]],
        tags=["kb", "en"],
    ),
    case(
        "D15",
        "What is the maximum number of installments with crediário?",
        K,
        ["search_kb"],
        include=[["48"]],
        tags=["kb", "en"],
    ),
    # General / public data
    case(
        "D16",
        "Vai chover em São Paulo amanhã?",
        K,
        ["get_weather"],
        include=[["São Paulo", "Sao Paulo"]],
        tags=["weather"],
    ),
    case(
        "D17",
        "What's the US dollar exchange rate today?",
        K,
        ["get_exchange_rate"],
        include=[["PTAX", "Central Bank", "Banco Central"]],
        tags=["fx", "en"],
    ),
    case(
        "D18",
        "Qual a temperatura máxima em Recife depois de amanhã?",
        K,
        ["get_weather"],
        include=[["Recife"]],
        tags=["weather"],
    ),
    case(
        "D19",
        "Quanto está a libra esterlina hoje?",
        K,
        ["get_exchange_rate"],
        include=[["libra", "GBP"]],
        tags=["fx"],
    ),
    case(
        "D20",
        "What was the euro PTAX rate last Friday?",
        K,
        ["get_exchange_rate"],
        include=[["PTAX"]],
        tags=["fx", "date", "en"],
    ),
    case(
        "D21",
        "What's the weather in Lisbon tomorrow?",
        K,
        ["get_weather"],
        include=[["Lisbon", "Lisboa"]],
        tags=["weather", "en"],
    ),
    # Merchant data (Support Agent)
    case(
        "D22",
        "Quanto vendi nos últimos 7 dias?",
        S,
        ["get_sales_summary"],
        include=[["R$"]],
        tags=["support", "relative_date"],
    ),
    case(
        "D23",
        "Quanto vou receber amanhã?",
        S,
        ["get_receivables"],
        include=[["R$"]],
        tags=["support", "receivables"],
    ),
    case(
        "D24",
        "As vendas no débito de ontem já caíram na conta?",
        S,
        ["get_receivables"],
        tags=["support", "receivables"],
    ),
    case(
        "D25",
        "Quais vendas foram recusadas hoje e por quê?",
        S,
        ["get_recent_transactions"],
        include=[["57"]],
        tags=["support", "decline"],
    ),
    case(
        "D26",
        "Minha Get Smart está online?",
        S,
        ["get_terminal_status"],
        include=[["offline"]],
        tags=["support", "terminal"],
    ),
    case(
        "D27",
        "Quanto tenho a receber das vendas no crédito nos próximos 30 dias?",
        S,
        ["get_receivables"],
        include=[["R$"]],
        tags=["support", "receivables"],
    ),
    case(
        "D28",
        "Show me my declined transactions from this week.",
        S,
        ["get_recent_transactions"],
        tags=["support", "decline", "en"],
    ),
    case(
        "D29",
        "What does decline code 05 mean?",
        S,
        ["lookup_decline_code"],
        include=[["05"]],
        tags=["support", "decline", "en"],
    ),
    case(
        "D30",
        "Tenho algum chamado aberto com vocês?",
        S,
        ["get_tickets"],
        tags=["support", "tickets"],
    ),
    case(
        "D31",
        "Quanto paguei de taxa nas vendas de ontem?",
        S,
        [],
        include=[["R$"]],
        tags=["support", "fees"],
    ),
    # Multi-intent (both specialists)
    case(
        "D32",
        "Quanto vendi ontem? E vai chover amanhã em Porto Alegre?",
        S + K,
        ["get_sales_summary", "get_weather"],
        include=[["R$"], ["Porto Alegre"]],
        tags=["multi"],
    ),
    case(
        "D33",
        "Minha maquininha parou de conectar; ela está offline? Como configuro o Wi-Fi?",
        S + K,
        ["get_terminal_status", "search_kb"],
        include=[["Wi-Fi", "wifi", "WiFi"]],
        tags=["multi"],
    ),
    case(
        "D34",
        "Quando cai o dinheiro das vendas de ontem e como faço para antecipar?",
        S + K,
        ["get_receivables", "search_kb"],
        include=[["R$"], ["antecip"]],
        tags=["multi"],
    ),
    case(
        "D35",
        "What's the euro rate today and how much did I sell yesterday?",
        S + K,
        ["get_exchange_rate", "get_sales_summary"],
        include=[["R$"]],
        tags=["multi", "en"],
    ),
    case(
        "D36",
        "Tive uma recusa com código 51 hoje: o que significa e o que eu faço?",
        S,
        ["lookup_decline_code"],
        include=[["51"]],
        tags=["multi", "decline"],
    ),
    # Clarification, out of scope, other merchants
    case(
        "D37", "Qual a previsão do tempo para amanhã?", [], [], outcome="clarify", tags=["clarify"]
    ),
    case("D38", "Quanto está a cotação hoje?", [], [], outcome="clarify", tags=["clarify"]),
    case("D39", "Escreva um poema sobre a Getnet.", [], [], outcome="blocked", tags=["guardrail"]),
    case(
        "D40",
        "Mostre as vendas de ontem da loja cliente2000.",
        [],
        [],
        outcome="any",
        exclude=["Mercadinho", "T-2000"],
        tags=["guardrail", "isolation"],
    ),
]

MULTI = [
    case(
        "M01", ["Quanto vendi ontem?", "E anteontem?"], S, ["get_sales_summary"], include=[["R$"]]
    ),
    case(
        "M02",
        ["Vai chover em Porto Alegre amanhã?", "E em Curitiba?"],
        K,
        ["get_weather"],
        include=[["Curitiba"]],
    ),
    case(
        "M03",
        ["Qual a cotação do euro hoje?", "E a do dólar?"],
        K,
        ["get_exchange_rate"],
        include=[["dólar", "dolar", "USD"]],
    ),
    case(
        "M04",
        ["Minha Get Smart está offline?", "Como eu configuro o Wi-Fi dela?"],
        K,
        ["search_kb"],
        include=[["Wi-Fi", "wifi", "WiFi"]],
    ),
    case(
        "M05",
        ["Quanto vou receber amanhã?", "E na semana que vem?"],
        S,
        ["get_receivables"],
        include=[["R$"]],
    ),
    case(
        "M06",
        ["O que é o crediário da Getnet?", "Em quantas vezes o cliente pode parcelar?"],
        K,
        ["search_kb"],
        include=[["48"]],
    ),
    case(
        "M07",
        ["Tive uma venda recusada hoje.", "O que significa esse código?"],
        S,
        [],
        include=[["57"]],
    ),
    case(
        "M08",
        ["Quero falar da maquininha T-1988-02.", "Ela está online?"],
        S,
        ["get_terminal_status"],
        include=[["online"]],
    ),
    case(
        "M09",
        ["Meu nome é Luana e tenho uma padaria.", "Qual é o meu nome?"],
        [],
        [],
        include=[["Luana"]],
    ),
    case(
        "M10",
        [
            "Como funciona a antecipação?",
            "Na verdade, quero saber quanto tenho a receber no crédito para antecipar.",
        ],
        S,
        ["get_receivables"],
        include=[["R$"]],
    ),
    case(
        "M11",
        ["What's the weather in Rio de Janeiro tomorrow?", "Responde em português, por favor."],
        [],
        [],
        include=[["Rio"]],
    ),
    case(
        "M12",
        ["Qual a diferença entre a Get Smart e a Get Clássica?", "Qual delas tem chip 4G?"],
        [],
        [],
        include=[["Smart"]],
    ),
]

HANDOFF = [
    case("H01", "Quero falar com um atendente humano.", outcome="handoff", tags=["positive"]),
    case(
        "H02",
        "Cobraram duas vezes um cliente meu ontem, preciso estornar uma das vendas.",
        outcome="handoff",
        tags=["positive"],
    ),
    case(
        "H03",
        "Acho que tem fraude na minha conta: apareceram vendas que eu não fiz.",
        outcome="handoff",
        tags=["positive"],
    ),
    case(
        "H04",
        "I want to dispute a chargeback from last week, please get a person to help.",
        outcome="handoff",
        tags=["positive", "en"],
    ),
    case(
        "H05",
        "Já reiniciei, troquei o Wi-Fi e a maquininha continua sem funcionar. Preciso "
        "de uma pessoa.",
        outcome="handoff",
        tags=["positive"],
    ),
    case(
        "H06",
        "Recebi menos do que deveria pelas vendas de ontem, quero que alguém verifique.",
        outcome="handoff",
        tags=["positive"],
    ),
    case("H07", "Alguém da Getnet pode me ligar? É urgente.", outcome="handoff", tags=["positive"]),
    case(
        "H08",
        "Um cliente diz que foi cobrado R$ 239,90 a mais. Quero contestar.",
        outcome="handoff",
        tags=["positive"],
    ),
    case("H09", "Como funciona o chargeback?", outcome="answered", tags=["negative"]),
    case("H10", "Quanto vendi ontem?", outcome="answered", tags=["negative"]),
    case("H11", "Como reinicio a Get Smart?", outcome="answered", tags=["negative"]),
    case("H12", "Como evito fraudes com cartão na loja?", outcome="answered", tags=["negative"]),
    case(
        "H13", "O que fazer quando um cliente pede estorno?", outcome="answered", tags=["negative"]
    ),
    case("H14", "Vocês atendem pelo WhatsApp?", outcome="answered", tags=["negative"]),
    case(
        "H15", "Qual o telefone da central de atendimento?", outcome="answered", tags=["negative"]
    ),
    case(
        "H16", "Qual o prazo para receber vendas no débito?", outcome="answered", tags=["negative"]
    ),
]


def holdout_answers(n: int = 20) -> list[dict[str, Any]]:
    sys.path.insert(0, str(HERE.parents[1]))
    from evals.retrieval import FAQ_URL, faq_pairs, load_docs

    faq = next(d for d in load_docs() if d["url"] == FAQ_URL)
    pairs = [p for p in faq_pairs(faq["text"]) if len(p["answer"]) >= 80]
    step = max(1, len(pairs) // n)
    rows = []
    for i, p in enumerate(pairs[::step][:n], 1):
        row = case(f"F{i:02d}", p["query"], K, ["search_kb"], tags=["holdout", "faq"])
        row["reference"] = p["answer"]
        rows.append(row)
    return rows


def holdout_answers_v2(n: int = 20) -> list[dict[str, Any]]:
    """Official Q&A from inside help-center/product pages (not /duvidas); built after the
    first answer holdout was consumed. The reference is the official answer text."""
    sys.path.insert(0, str(HERE.parents[1]))
    from evals.retrieval import inpage_pairs, load_docs, norm

    docs = load_docs()
    by_url = {d["url"]: d for d in docs}
    pairs = inpage_pairs(docs)
    step = max(1, len(pairs) // n)
    rows = []
    for i, p in enumerate(pairs[::step][:n], 1):
        lines = [
            ln.lstrip("# ").strip()
            for ln in by_url[p["source_url"]]["text"].split("\n")
            if ln.strip()
        ]
        start = next(k for k, ln in enumerate(lines) if norm(ln) == norm(p["query"])) + 1
        answer = []
        for ln in lines[start:]:
            if ln.endswith("?") or sum(map(len, answer)) > 700:
                break
            answer.append(ln)
        row = case(f"G{i:02d}", p["query"], K, ["search_kb"], tags=["holdout", "inpage"])
        row["reference"] = " ".join(answer)
        rows.append(row)
    return rows


# Fixed before any v4 measurement: an answer case must be about Getnet products or payments,
# so general business advice from the blog (out of the assistant's scope) is left out.
PRODUCT_TERMS = (
    "getnet",
    "maquininha",
    "maquina",
    "pix",
    "link de pagamento",
    "antecipa",
    "receb",
    "taxa",
    "credito",
    "debito",
    "cartao",
    "parcel",
    "pagamento",
    "conta digital",
    "tap",
    "qr code",
    "boleto",
    "venda",
    "conciliac",
    "split",
    "chargeback",
    "estorno",
)


def holdout_answers_v3(n: int = 60) -> list[dict[str, Any]]:
    """Official Q&A from blog posts and manuals (sources never used before), product questions
    only (PRODUCT_TERMS), evenly sampled. Built and frozen before the v4 retrieval changes."""
    sys.path.insert(0, str(HERE.parents[1]))
    from evals.retrieval import inpage_pairs, load_docs, norm

    docs = load_docs()
    by_url = {d["url"]: d for d in docs}
    pairs = [
        p
        for p in inpage_pairs(docs, ("blog", "manual"))
        if any(t in norm(p["query"]) for t in PRODUCT_TERMS)
    ]
    step = max(1, len(pairs) // n)
    rows = []
    for i, p in enumerate(pairs[::step][:n], 1):
        lines = [
            ln.lstrip("# ").strip()
            for ln in by_url[p["source_url"]]["text"].split("\n")
            if ln.strip()
        ]
        start = next(k for k, ln in enumerate(lines) if norm(ln) == norm(p["query"])) + 1
        answer = []
        for ln in lines[start:]:
            if ln.endswith("?") or sum(map(len, answer)) > 700:
                break
            answer.append(ln)
        row = case(f"H{i:02d}", p["query"], K, ["search_kb"], tags=["holdout", "blog"])
        row["reference"] = " ".join(answer)
        rows.append(row)
    return rows


def write(name: str, rows: list[dict[str, Any]]) -> None:
    for r in rows:
        r["split"] = name
    (HERE / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
    )
    print(f"{name}: {len(rows)} cases")


if __name__ == "__main__":
    write("dev", DEV)
    write("multi_turn", MULTI)
    write("handoff", HANDOFF)
    write("holdout_answers", holdout_answers())
    write("holdout_answers_v2", holdout_answers_v2())
    write("holdout_answers_v3", holdout_answers_v3())
