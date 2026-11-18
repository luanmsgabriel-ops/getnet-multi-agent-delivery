"""Read access to merchant data. Ownership and scopes are enforced here, not by callers.

Every query is filtered by the authenticated principal; there is no way to pass another
merchant id. The Support Agent tools are thin wrappers over this repository.
"""

from datetime import date
from typing import Any

from app.data.db import Database
from app.security.auth import Principal, require_scope

_RECEIVABLES = (
    "SELECT r.*, s.method, s.sold_at FROM receivables r JOIN sales s ON s.id = r.sale_id "
    "WHERE r.merchant_id = ? AND "
)
_RECEIVABLES_BY_PAYMENT = _RECEIVABLES + "r.expected_date BETWEEN ? AND ? ORDER BY r.expected_date"
_RECEIVABLES_BY_SALE = (
    _RECEIVABLES + "substr(s.sold_at, 1, 10) BETWEEN ? AND ? ORDER BY r.expected_date"
)


class SupportRepository:
    def __init__(self, db: Database, principal: Principal) -> None:
        self._db = db
        self._p = principal

    def merchant(self) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM merchants WHERE id = ?", (self._p.sub,)).fetchone()
        return None if row is None else dict(row)

    def sales(
        self, date_from: date, date_to: date, status: str | None = None
    ) -> list[dict[str, Any]]:
        require_scope(self._p, "sales:read")
        sql = "SELECT * FROM sales WHERE merchant_id = ? AND substr(sold_at, 1, 10) BETWEEN ? AND ?"
        args: list[Any] = [self._p.sub, date_from.isoformat(), date_to.isoformat()]
        if status:
            sql += " AND status = ?"
            args.append(status)
        with self._db.connect() as conn:
            rows = conn.execute(sql + " ORDER BY sold_at", args).fetchall()
        return [dict(r) for r in rows]

    def recent_transactions(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        require_scope(self._p, "sales:read")
        sql = "SELECT * FROM sales WHERE merchant_id = ?"
        args: list[Any] = [self._p.sub]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY sold_at DESC LIMIT ?"
        args.append(max(1, min(limit, 50)))
        with self._db.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def receivables(
        self, date_from: date, date_to: date, by: str = "payment_date"
    ) -> list[dict[str, Any]]:
        """Receivables whose payment date (or originating sale date) falls in the range."""
        require_scope(self._p, "receivables:read")
        sql = _RECEIVABLES_BY_SALE if by == "sale_date" else _RECEIVABLES_BY_PAYMENT
        with self._db.connect() as conn:
            rows = conn.execute(
                sql, (self._p.sub, date_from.isoformat(), date_to.isoformat())
            ).fetchall()
        return [dict(r) for r in rows]

    def terminals(self, terminal_id: str | None = None) -> list[dict[str, Any]]:
        require_scope(self._p, "terminal:read")
        sql = "SELECT * FROM terminals WHERE merchant_id = ?"
        args: list[Any] = [self._p.sub]
        if terminal_id:
            sql += " AND id = ?"
            args.append(terminal_id)
        with self._db.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def decline_code(self, code: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM decline_codes WHERE code = ?", (code,)).fetchone()
        return None if row is None else dict(row)
