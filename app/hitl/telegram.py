"""Telegram channel for operators: handoff notifications and replies by command.

- Every handoff (and every missed deadline) is sent to the operators' chats, with the priority,
  the deadline, a short redacted summary and a link to the console.
- An operator can answer from Telegram with `/reply <id> <text>`, `/instruct <id> <text>` or
  `/close <id> <text>`, and list the queue with `/fila`. Commands go through the same path as
  the console (Orchestrator.resume): the same guardrail, idempotency and audit trail.
- Only chats listed in TELEGRAM_OPERATOR_CHAT_IDS are served; a message from any other chat is
  ignored and its chat id is logged, which is how an operator's chat is first registered.
- Updates are read by long polling, so no public URL is needed. Run the poller in one replica
  only (TELEGRAM_POLLING), since Telegram serves updates to one reader at a time.

Telegram is a third-party service: messages carry ids, reason, priority and a redacted summary,
never card numbers, CPF, e-mail or phone.
"""

import logging
import re
import threading
from collections.abc import Callable
from typing import Any

import httpx2 as httpx

from app.security.guardrails import redact

log = logging.getLogger("getnet.telegram")

Api = Callable[[str, dict[str, Any]], dict[str, Any]]
# (operator, action, handoff_id, text) -> reply shown to the operator
CommandHandler = Callable[[str, str, str, str], str]
QueueProvider = Callable[[], list[dict[str, Any]]]

ACTIONS = {"/reply": "reply", "/instruct": "instruct", "/close": "close"}
COMMAND = re.compile(r"^(/\w+)(?:@\w+)?(?:\s+(H-[0-9A-F]{6}))?(?:\s+(.+))?$", re.DOTALL)
PRIORITY_LABEL = {"urgent": "URGENTE", "high": "alta", "normal": "normal"}
HELP = (
    "Comandos:\n"
    "/fila: transbordos pendentes\n"
    "/reply H-XXXXXX texto: resposta para o lojista\n"
    "/instruct H-XXXXXX texto: orientação para o assistente (ele pode consultar dados)\n"
    "/close H-XXXXXX texto: encerra o caso com uma nota final"
)


def _summary(text: str, limit: int = 300) -> str:
    clean, _ = redact(text)
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def format_event(event: str, data: dict[str, Any], console_url: str) -> str:
    hid = data.get("handoff_id", "?")
    if event == "handoff.sla_breached":
        head = f"⏰ Prazo vencido: {hid} sem resposta. Prioridade elevada para URGENTE."
    else:
        priority = PRIORITY_LABEL.get(str(data.get("priority")), str(data.get("priority")))
        head = f"🔔 Novo transbordo {hid} · prioridade {priority} · motivo {data.get('reason')}"
    lines = [head, f"Lojista: {data.get('merchant_id', '?')}"]
    if data.get("due_at"):
        lines.append(f"Responder até: {data['due_at']} (UTC)")
    if data.get("summary"):
        lines.append(f"Resumo: {_summary(str(data['summary']))}")
    lines.append(f"Console: {console_url}#{hid}")
    lines.append(f"Responder aqui: /reply {hid} <texto>")
    return "\n".join(lines)


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_ids: frozenset[int],
        console_url: str,
        api: Api | None = None,
    ) -> None:
        self.chat_ids = chat_ids
        self.console_url = console_url
        self._token = token
        self._api = api or self._http
        self._offset = 0

    def _http(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = float(payload.get("timeout", 0)) + 10.0
        response = httpx.post(
            f"https://api.telegram.org/bot{self._token}/{method}", json=payload, timeout=timeout
        )
        data: dict[str, Any] = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method} failed: {data.get('description', '?')}")
        return data

    def send(self, chat_id: int, text: str) -> bool:
        try:
            self._api("sendMessage", {"chat_id": chat_id, "text": text[:4000]})
            return True
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            log.warning("telegram_send_failed", extra={"fields": {"error": str(exc)[:200]}})
            return False

    def notify(self, event: str, data: dict[str, Any]) -> bool:
        """Send to every operator chat; True if at least one delivery worked."""
        text = format_event(event, data, self.console_url)
        results = [self.send(chat_id, text) for chat_id in sorted(self.chat_ids)]
        return any(results)

    # -- incoming commands ----------------------------------------------------------------
    def handle(
        self, update: dict[str, Any], on_command: CommandHandler, queue: QueueProvider
    ) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = str(message.get("text") or "").strip()
        if chat_id is None or not text:
            return
        if chat_id not in self.chat_ids:
            log.warning("telegram_unknown_chat", extra={"fields": {"chat_id": chat_id}})
            return
        sender = message.get("from") or {}
        operator = f"telegram:{sender.get('username') or sender.get('id', chat_id)}"
        self.send(chat_id, self.answer(text, operator, on_command, queue))

    def answer(
        self, text: str, operator: str, on_command: CommandHandler, queue: QueueProvider
    ) -> str:
        match = COMMAND.match(text)
        if match is None:
            return HELP
        command, handoff_id, body = match.group(1).lower(), match.group(2), match.group(3)
        if command in ("/fila", "/queue"):
            pending = queue()
            if not pending:
                return "Nenhum transbordo pendente."
            return "\n".join(
                f"{h['id']} · {PRIORITY_LABEL.get(h['priority'], h['priority'])} · "
                f"{h['reason']} · {h['merchant_id']}"
                for h in pending[:20]
            )
        action = ACTIONS.get(command)
        if action is None:
            return HELP
        if handoff_id is None or not body or not body.strip():
            return f"Uso: {command} H-XXXXXX texto"
        return on_command(operator, action, handoff_id, body.strip())

    def poll_once(self, on_command: CommandHandler, queue: QueueProvider, wait_s: int = 25) -> int:
        data = self._api(
            "getUpdates",
            {"offset": self._offset, "timeout": wait_s, "allowed_updates": ["message"]},
        )
        updates = data.get("result") or []
        for update in updates:
            self._offset = max(self._offset, int(update["update_id"]) + 1)
            try:
                self.handle(update, on_command, queue)
            except Exception:  # one bad update must not stop the poller
                log.exception("telegram_update_failed")
        return len(updates)

    def run(self, stop: threading.Event, on_command: CommandHandler, queue: QueueProvider) -> None:
        backoff = 1.0
        while not stop.is_set():
            try:
                self.poll_once(on_command, queue)
                backoff = 1.0
            except Exception as exc:
                log.warning("telegram_poll_failed", extra={"fields": {"error": str(exc)[:200]}})
                stop.wait(backoff)
                backoff = min(backoff * 2, 60.0)
