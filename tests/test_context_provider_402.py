"""Synthetic provider failure regression. No live provider, credentials or cost."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from app.context_client import ModelClient
from app.context_service import ContextService
from app.context_solo import SoloInterpreter
from app.context_store import Store

class Provider402Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="getnet-402-")
        self.root = Path(self.tmp.name)
        self.client = ModelClient(self.root / "ledger.json", "synthetic-not-a-key",
            {"prompt": "0.000002", "completion": "0.000010"}, model="openai/gpt-6-sol", max_cost="1.00")
    def tearDown(self):
        self.tmp.cleanup()
    def transport(self):
        mocked = patch("app.context_client.httpx.Client")
        factory = mocked.start()
        self.addCleanup(mocked.stop)
        transport = factory.return_value.__enter__.return_value
        transport.post.return_value = httpx.Response(402, json={"error": "SYNTHETIC_PRIVATE_UPSTREAM_BODY"})
        return transport
    def test_402_reserves_unknown_cost_and_blocks_retry(self):
        transport = self.transport()
        schema = {"type": "object", "properties": {}}
        with self.assertRaises(RuntimeError):
            self.client.complete("synthetic", {"message": "test"}, schema)
        ledger = json.loads(self.client.path.read_text("utf-8"))
        self.assertEqual(ledger["halted"], "unknown_cost")
        self.assertEqual(len(ledger["calls"]), 1)
        self.assertEqual(ledger["calls"][0]["http_status"], 402)
        self.assertEqual(ledger["calls"][0]["status"], "unknown_cost")
        self.assertNotIn("SYNTHETIC_PRIVATE_UPSTREAM_BODY", self.client.path.read_text("utf-8"))
        with self.assertRaisesRegex(RuntimeError, "Ledger halted"):
            self.client.complete("synthetic", {"message": "test"}, schema)
        self.assertEqual(transport.post.call_count, 1)
        self.assertEqual(json.loads(self.client.path.read_text("utf-8")), ledger)
    def test_402_preserves_memory_and_discloses_fallback(self):
        transport = self.transport()
        store = Store(self.root / "state.db")
        service = ContextService(store, SoloInterpreter(self.client))
        sid = service.create("synthetic_A")
        message = "A Smart do caixa da Loja Um está sem internet."
        proposal = {"devices": [{"ref": "a", "label": "Smart do caixa", "store": "Loja Um", "quote": message}],
            "observations": [{"entity": "a", "incident": "internet1", "scope": "entity", "subject": "device",
                "field": "connected", "value": "false", "status": "asserted", "origin": "customer", "quote": message}],
            "requests": [{"kind": "summary", "topic": "connectivity", "entities": ["a"], "quote": message}],
            "focus": ["a"], "resolve_pending": []}
        service.step("synthetic_A", sid, message, proposal=proposal)
        before = store.read("synthetic_A", sid)
        self.assertTrue(before[1]["facts"])
        result = service.step("synthetic_A", sid, "Como configurar o Wi-Fi da maquininha Getnet?")
        self.assertEqual(result["mode"], "fallback_extractive")
        self.assertIn("Não consegui atualizar o contexto", result["answer"])
        self.assertEqual(store.read("synthetic_A", sid), before)
        self.assertEqual(result["state"], before[1])
        self.assertEqual(transport.post.call_count, 1)

if __name__ == "__main__":
    unittest.main()
