"""Testes unitarios sinteticos, sem Docker/k6/estressores, para a seguranca do pipeline."""
from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DataPipelineTests(unittest.TestCase):
    def test_k6_json_whitespace_is_accepted(self):
        module = load_module("analyze_run", ROOT / "scripts/analyze_run.py")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "sample.jsonl"
            f.write_text(json.dumps({"type": "Point", "metric": "failed", "data": {
                "time": "2026-10-20T12:00:00Z", "value": 0}}, indent=None) + "\n", encoding="utf-8")
            a, ok, dr = module.load_k6(str(f))
            self.assertEqual(len(a), 1)
            self.assertEqual(ok, [])

    def make_run(self, root: Path, ident: str, status: str, repetition: str = "r01", failmarker: bool = False):
        run = root / ident
        (run / "analysis").mkdir(parents=True)
        (run / "manifest.json").write_text(json.dumps({"scenario":"C0", "repetition": repetition}), encoding="utf-8")
        with (run / "analysis" / "phases.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["cenario", "repeticao", "fase", "p95_ms", "p99_ms",
                    "erro_composto_pct", "vazao_sucesso_rps", "vazao_observada_rps", "disponibilidade_pct",
                    "cobertura_pct", "respostas_corretas", "dropped_iterations"])
            writer.writeheader()
            writer.writerow(dict(cenario="C0", repeticao=repetition, fase="util", p95_ms=12,
                p99_ms=17, erro_composto_pct=0, vazao_sucesso_rps=5,
                vazao_observada_rps=5, disponibilidade_pct=100, cobertura_pct=100,
                respostas_corretas=15, dropped_iterations=0))
        (run / "notes.md").write_text(f"# Execucao\n- Classificacao final: {status}\n" +
            ("INVALIDA: falha tecnica\n" if failmarker else ""), encoding="utf-8")
        return run

    def consolidate(self, src, dest):
        return subprocess.run([sys.executable, str(ROOT / "scripts/consolidate.py"),str(src),str(dest)],
                              capture_output=True, text=True)

    def test_no_pending_or_invalid_run_is_consolidated(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "runs"
            self.make_run(src,"C0-r01-a","PENDENTE")
            self.make_run(src,"C0-r02-b","INVALIDA", "r02")
            self.make_run(src,"C0-r03-c","VALIDA", "r03", failmarker=True)
            out = Path(d) / "out"
            p = self.consolidate(src,out)
            self.assertEqual(p.returncode,1,p.stderr)
            self.assertFalse((out/"summary-runs.csv").exists())

    def test_valid_approval_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "runs"
            self.make_run(src,"C0-r01-a","VALIDA")
            self.make_run(src,"C0-r02-b","PENDENTE", "r02")
            out = Path(d) / "out"
            p = self.consolidate(src,out)
            self.assertEqual(p.returncode,0,(p.stdout,p.stderr))
            with (out / "summary-runs.csv").open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["repeticao"],"r01")

    def test_duplicate_approved_repetition_fails(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "runs"
            self.make_run(src,"C0-r01-a","VALIDA")
            self.make_run(src,"C0-r01-b","VALIDA")
            out = Path(d) / "out"
            p = self.consolidate(src,out)
            self.assertEqual(p.returncode,2,(p.stdout,p.stderr))
            self.assertFalse((out/"summary-runs.csv").exists())


if __name__ == "__main__":
    unittest.main()
