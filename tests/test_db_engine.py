#!/usr/bin/env python3
"""
Automated unit tests for the Context Graph & Query Cache plugin (server/db_engine.py).
Tests:
  - Static AST/regex indexing & SHA-256 staleness detection
  - Automatic secret redaction (redact_secrets)
  - Cost per feature attribution (derive_feature_info & estimate_token_cost)
  - Ground-truth overrides & team-shareable .context-graph/overrides.json export/import
  - Hallucination verification & auto-repair (verify_and_fix_hallucinations)
"""

import os
import sys
import tempfile
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from server import db_engine


class TestContextGraphEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_cache.db")
        os.environ["CONTEXT_GRAPH_DB_PATH"] = self.db_path
        self.ws_dir = os.path.join(self.tmp_dir.name, "sample_repo")
        os.makedirs(self.ws_dir, exist_ok=True)

    def tearDown(self) -> None:
        os.environ.pop("CONTEXT_GRAPH_DB_PATH", None)
        self.tmp_dir.cleanup()

    def test_redact_secrets(self) -> None:
        raw = (
            "Connect to mongodb+srv://admin:SuperSecret123@cluster0.example.net/db "
            "and postgresql://mcp_readonly:AVNS_SecretToken99@pg.example.com:25060/defaultdb"
        )
        scrubbed = db_engine.redact_secrets(raw)
        self.assertNotIn("SuperSecret123", scrubbed)
        self.assertNotIn("AVNS_SecretToken99", scrubbed)
        self.assertIn("[REDACTED]", scrubbed)

    def test_estimate_token_cost_and_feature_derivation(self) -> None:
        # Without plugin usage (plugin_tokens_saved=0), plugin savings must be strictly $0.00
        cost_no_plugin = db_engine.estimate_token_cost(
            model_name="Gemini 4 Argon (Medium)",
            input_tokens=1_000_000,
            cache_read_tokens=4_000_000,
            output_tokens=100_000,
            plugin_tokens_saved=0,
        )
        # 1M * $1.25 + 4M * $0.3125 + 0.1M * $5.00 = $1.25 + $1.25 + $0.50 = $3.00
        self.assertAlmostEqual(cost_no_plugin["estimated_cost_usd"], 3.00, places=2)
        self.assertEqual(cost_no_plugin["estimated_cache_savings_usd"], 0.00)

        # With plugin usage saving 2M input tokens (2M * $1.25 = $2.50 saved)
        cost_with_plugin = db_engine.estimate_token_cost(
            model_name="Gemini 4 Argon (Medium)",
            input_tokens=1_000_000,
            cache_read_tokens=4_000_000,
            output_tokens=100_000,
            plugin_tokens_saved=2_000_000,
        )
        self.assertAlmostEqual(cost_with_plugin["estimated_cache_savings_usd"], 2.50, places=2)
        self.assertAlmostEqual(cost_with_plugin["uncached_cost_usd"], 5.50, places=2)


        f1 = db_engine.derive_feature_info(
            "fa", "1643-foundation-batch-associate-and-quit-logic", "some prompt"
        )
        f2 = db_engine.derive_feature_info(
            "brocamp/tool-v3-server",
            "584-foundation-batch-associate-and-quit-logic",
            "another prompt",
        )
        self.assertEqual(f1["feature_key"], f2["feature_key"])
        self.assertEqual(f1["feature_name"], "foundation-batch-associate-and-quit-logic")
        self.assertEqual(f1["ticket_id"], "#1643")
        self.assertEqual(f2["ticket_id"], "#584")

    def test_index_verify_and_overrides_export_import(self) -> None:
        py_file = os.path.join(self.ws_dir, "service.py")
        with open(py_file, "w", encoding="utf-8") as f:
            f.write("class PaymentProcessor:\n    def charge(self):\n        return True\n")

        idx = db_engine.auto_index_workspace(self.ws_dir)
        self.assertEqual(idx["discovered_files"], 1)
        self.assertEqual(idx["indexed_or_updated"], 1)

        # Inject a hallucinated symbol and verify auto-fix removes it
        db_engine.upsert_file(
            workspace_path=self.ws_dir,
            file_path=py_file,
            summary="Payment service",
            symbols=[
                {"name": "PaymentProcessor", "kind": "class", "line": 1},
                {"name": "non_existent_hallucinated_fn", "kind": "function", "line": 99},
            ],
        )
        ver = db_engine.verify_and_fix_hallucinations(self.ws_dir, auto_fix=True)
        self.assertGreaterEqual(ver["issues_found"], 1)
        self.assertGreaterEqual(ver["auto_fixed"], 1)

        # Record & export/import ground-truth override
        db_engine.record_correction(
            workspace_path=self.ws_dir,
            override_key="api-timeout-ms",
            verified_truth="DEFAULT_TIMEOUT_MS must be 5000 in production",
            hallucination_or_mistake="Assuming 30000ms",
            priority="critical",
        )
        exp = db_engine.export_overrides_to_file(self.ws_dir)
        self.assertEqual(exp["exported_count"], 1)
        self.assertTrue(os.path.isfile(exp["file_path"]))

        imp = db_engine.import_overrides_from_file(self.ws_dir)
        self.assertEqual(imp["imported_count"], 1)


if __name__ == "__main__":
    unittest.main()
