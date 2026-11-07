"""Testes offline das automacoes do TCC2 (sem Docker, k6 ou servidor).

Cobre: revisao automatica, calibracao das taxas, metas (SLO), figuras, tabelas, geracao de
resultados em um comando e o executor da campanha. Usa execucoes SINTETICAS
(tests/synthetic_runs.py, modo rapido) e verifica que dado sintetico nunca sai sem marcacao.
Rodar da raiz:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import synthetic_runs  # noqa: E402
import run_campaign  # noqa: E402
import revisar_execucoes  # noqa: E402
from run_context import janelas_p95, ler_vmstat  # noqa: E402


def py(*args, cwd=ROOT):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=cwd)


def ler_csv(caminho):
    with open(caminho, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ler_json(caminho):
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


def decidir_inconclusivas(campanha: Path) -> None:
    """Simula a decisao do operador: aprova as execucoes que ficaram INCONCLUSIVAS."""
    for n in campanha.glob("*/notes.md"):
        txt = n.read_text(encoding="utf-8")
        if "DECISAO DO OPERADOR" in txt:
            n.write_text(txt.replace("- Classificacao final: PENDENTE", "- Classificacao final: VALIDA"),
                         encoding="utf-8")


class PipelineSintetico(unittest.TestCase):
    """Fluxo completo: revisao -> decisao do operador -> consolidacao -> figuras e tabelas."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.r = synthetic_runs.gerar_tudo(cls.base, rapido=True)
        p = py(ROOT / "scripts/revisar_execucoes.py", cls.r["campanha"], "--aplicar", "--sim")
        assert p.returncode == 0, p.stdout + p.stderr
        cls.saida_revisao = p.stdout
        decidir_inconclusivas(cls.r["campanha"])
        p = py(ROOT / "scripts/consolidate.py", cls.r["campanha"], cls.base / "processed")
        assert p.returncode == 0, p.stdout + p.stderr
        cls.resumo = cls.base / "processed" / "summary-runs.csv"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_dir(self, prefixo):
        return next(p for p in self.r["execucoes"] if p.name.startswith(prefixo) and
                    "INVALIDA:" not in (p / "notes.md").read_text())

    def test_revisao_propostas(self):
        self.assertIn("propostas: 17 VALIDA, 1 INVALIDA, 1 INCONCLUSIVA", self.saida_revisao)
        inval = next(p for p in self.r["execucoes"] if "INVALIDA:" in (p / "notes.md").read_text())
        self.assertIn("- Classificacao final: INVALIDA", (inval / "notes.md").read_text())
        ok = (self.run_dir("SINT-C0-r01") / "notes.md").read_text()
        self.assertIn("- Classificacao final: VALIDA", ok)
        self.assertIn("- Revisao automatica:", ok)
        self.assertIn("Validade da carga (k6 exit, dropped_iterations, CPU do notebook): k6 codigo 0", ok)

    def test_revisao_detecta_arquivo_alterado(self):
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / "run"
            shutil.copytree(self.run_dir("SINT-C4-r01"), copia)
            with open(copia / "k6-raw.json", "a", encoding="utf-8") as fh:
                fh.write("\n")
            r = revisar_execucoes.avaliar(str(copia), {})
            self.assertEqual(r["proposta"], "INVALIDA")
            self.assertTrue(any("integridade" in m for m in r["invalidos"]))

    def test_consolidacao_tem_taxa_e_tipo(self):
        rows = ler_csv(self.resumo)
        self.assertTrue(all(r["taxa_ofertada_rps"] for r in rows))
        self.assertTrue(all(r["tipo"] == "synthetic" for r in rows))
        self.assertEqual(len({r["run_id"] for r in rows}), 18)  # a invalida ficou de fora
        self.assertNotIn("C1", {r["cenario"] for r in rows})

    def test_figura_carga(self):
        out = self.base / "charts" / "fig03.png"
        p = py(ROOT / "scripts/fig_carga.py", self.resumo, "--saida", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        fonte = ler_json(str(out) + ".fonte.json")
        self.assertTrue(fonte["dados_sinteticos"])
        self.assertEqual(fonte["parametros"]["cenarios"], ["C0", "C2", "C3"])

    def test_figuras_perturbacao(self):
        for pref, tipo in (("SINT-C4-r01", "fig4"), ("SINT-C4-r02", "cpu"), ("SINT-C5-r01", "auto"),
                           ("SINT-C6-r01", "auto")):
            out = self.base / "charts" / f"{pref}-{tipo}.png"
            p = py(ROOT / "scripts/fig_perturbacao.py", self.run_dir(pref), "--tipo", tipo, "--saida", out,
                   "--janela", "5")
            self.assertEqual(p.returncode, 0, (pref, p.stderr))
            self.assertTrue(ler_json(str(out) + ".fonte.json")["dados_sinteticos"])

    def test_figura_perturbacao_recusa_cenario_de_carga(self):
        p = py(ROOT / "scripts/fig_perturbacao.py", self.run_dir("SINT-C0-r01"), "--saida", self.base / "x.png")
        self.assertEqual(p.returncode, 1)

    def test_rampa(self):
        p = py(ROOT / "scripts/analyze_ramp.py", self.r["rampa"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("JOELHO", p.stdout)
        out = self.base / "charts" / "C10.png"
        p = py(ROOT / "scripts/fig_rampa.py", self.r["rampa"], "--saida", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.base / "charts" / "C10-degraus.csv").exists())

    def test_tabelas_sem_metas_nao_inventam_veredito(self):
        saida = self.base / "tab-sem-meta"
        p = py(ROOT / "scripts/tabelas_artigo.py", "--resumo", self.resumo, "--runs", self.r["campanha"],
               "--slo", ROOT / "experiments/scenarios/slo.env", "--saida", saida)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("AVISO", p.stdout)
        with open(saida / "SINTETICO_quadro3-sli-slo.csv", encoding="utf-8") as fh:
            q = list(csv.reader(fh))
        self.assertEqual(q[1][2], "—")  # P95 sem meta congelada
        self.assertTrue((saida / "SINTETICO_tabelas-artigo.md").read_text().startswith("> **DADOS SINT"))

    def test_tabelas_com_metas(self):
        slo = self.base / "slo.env"
        slo.write_text("SLO_P95_MS=75\nSLO_P99_MS=100\n", encoding="utf-8")
        saida = self.base / "tab"
        p = py(ROOT / "scripts/tabelas_artigo.py", "--resumo", self.resumo, "--runs", self.r["campanha"],
               "--slo", slo, "--saida", saida)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(saida / "SINTETICO_quadro3-sli-slo.csv", encoding="utf-8") as fh:
            q = {li[0]: li[2] for li in csv.reader(fh)}
        self.assertTrue(q["Conjunto dos critérios"].endswith("/18"))
        a2 = ler_csv(saida / "SINTETICO_apendiceA2-auditoria.csv")
        self.assertEqual(len(a2), 19)  # inclui a execucao invalida
        self.assertEqual(sum(1 for r in a2 if r["estado"] == "INVALIDA (auto)"), 1)

    def test_derive_slo(self):
        p = py(ROOT / "scripts/derive_slo.py", self.r["campanha"], "--cenario", "SINT-C0")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout, r"SLO_P95_MS=\d+")
        self.assertIn("nada foi gravado", p.stdout)

    def test_gerar_resultados_em_um_comando(self):
        d = self.base / "resultados"
        slo = d / "slo.env"
        d.mkdir()
        slo.write_text("SLO_P95_MS=75\nSLO_P99_MS=100\n", encoding="utf-8")
        p = py(ROOT / "scripts/gerar_resultados.py", "--runs", self.r["campanha"], "--rampa", self.r["rampa"],
               "--processados", d / "processed", "--figuras", d / "charts", "--slo", slo,
               "--copiar-para", d / "windows")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for f in ("fig03-carga.png", "fig04-c4-temporal.png", "C10-rampa.png", "C12-cpu.png", "C13-memoria.png",
                  "C14-rede.png", "escolhas.json"):
            self.assertTrue((d / "charts" / f).exists(), f)
            self.assertTrue((d / "windows" / f).exists(), f)
        self.assertTrue((d / "windows" / "tabelas" / "SINTETICO_tabelas-artigo.md").exists())
        esc = ler_json(d / "charts" / "escolhas.json")["escolhas"]
        deltas = sorted(c["delta_p95_ms"] for c in esc["C4"]["candidatas"])
        self.assertEqual(esc["C4"]["delta_p95_ms"], deltas[1])  # mediana de 3
        self.assertEqual(len(list(d.glob("resultados-*.md"))), 1)


class Calibracao(unittest.TestCase):
    """calibrar_taxas.py e derive_slo.py --gravar em uma copia dos arquivos de cenario."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.r = synthetic_runs.gerar_tudo(self.base, rapido=True)
        self.cen = self.base / "scenarios"
        shutil.copytree(ROOT / "experiments" / "scenarios", self.cen)
        (self.cen / "common.env").write_text("PROTOCOL_VERSION=v1-rascunho\n", encoding="utf-8")
        self.args = ["--cenarios-dir", self.cen, "--protocolo", self.cen / "protocol-v1.md",
                     "--common", self.cen / "common.env"]

    def tearDown(self):
        self.tmp.cleanup()

    def rate(self, cen):
        return run_campaign.ler_env(str(self.cen / f"{cen}.env"))["RATE"]

    def test_propoe_sem_gravar(self):
        antes = self.rate("C0")
        p = py(ROOT / "scripts/calibrar_taxas.py", self.r["rampa"], *self.args)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Cap (maior degrau estavel antes do joelho) = 60 RPS", p.stdout)
        self.assertEqual(self.rate("C0"), antes)

    def test_grava_taxas_e_protocolo(self):
        p = py(ROOT / "scripts/calibrar_taxas.py", self.r["rampa"], *self.args, "--aplicar", "--sim")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.rate("C0"), self.rate("C2"), self.rate("C3")), ("14", "27", "45"))
        for c in ("C4", "C5", "C6", "C7"):
            self.assertEqual(self.rate(c), "14")
        prot = (self.cen / "protocol-v1.md").read_text(encoding="utf-8")
        self.assertIn("Cap = 60 RPS", prot)
        self.assertIn("C0 = R0 = 14 RPS; C2 = 27 RPS; C3 = 45 RPS", prot)

    def test_metas_gravadas(self):
        slo = self.cen / "slo.env"
        p = py(ROOT / "scripts/derive_slo.py", self.r["campanha"], "--cenario", "SINT-C0", "--gravar", "--sim",
               "--slo", slo, "--protocolo", self.cen / "protocol-v1.md", "--common", self.cen / "common.env")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        env = run_campaign.ler_env(str(slo))
        self.assertEqual((env["SLO_P95_MS"], env["SLO_P99_MS"]), ("75", "100"))
        prot = (self.cen / "protocol-v1.md").read_text(encoding="utf-8")
        self.assertIn("P95 <= 75 ms; P99 <= 100 ms", prot)
        self.assertIn("aplicadas a fase util", prot)  # o restante da linha foi preservado

    def test_protocolo_congelado_recusa_mudancas(self):
        (self.cen / "common.env").write_text("PROTOCOL_VERSION=v1\n", encoding="utf-8")
        p = py(ROOT / "scripts/calibrar_taxas.py", self.r["rampa"], *self.args, "--aplicar", "--sim")
        self.assertEqual(p.returncode, 3)
        p = py(ROOT / "scripts/derive_slo.py", self.r["campanha"], "--cenario", "SINT-C0", "--gravar", "--sim",
               "--slo", self.cen / "slo.env", "--protocolo", self.cen / "protocol-v1.md",
               "--common", self.cen / "common.env")
        self.assertEqual(p.returncode, 3)


class Utilitarios(unittest.TestCase):
    def test_vmstat_exige_horario_utc(self):
        with tempfile.TemporaryDirectory() as d:
            cab = ("procs -----------memory---------- ---swap-- -----io---- -system-- -------cpu------- "
                   "-----timestamp-----\n r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy "
                   "id wa st gu                 {tz}\n")
            linha = " 0  0      0 7769768   1144 172720    0    0   645    11   85    0  1  0 {id}  0  0  0 {h}\n"
            f = Path(d) / "v.txt"
            f.write_text(cab.format(tz="UTC") + linha.format(id=99, h="2026-11-07 02:42:55")
                         + linha.format(id=60, h="2026-11-07 02:43:00"), encoding="utf-8")
            pts = ler_vmstat(str(f))
            self.assertEqual(len(pts), 1)       # 1a linha (media desde o boot) descartada
            self.assertEqual(pts[0][1], 40.0)
            f.write_text(cab.format(tz="-03") + linha.format(id=99, h="2026-11-07 02:42:55")
                         + linha.format(id=60, h="2026-11-07 02:43:00"), encoding="utf-8")
            self.assertEqual(ler_vmstat(str(f)), [])  # fuso local: nao alinha

    def test_janela_com_poucas_amostras_fica_indefinida(self):
        regs = [(0.1 * i, 10.0) for i in range(30)] + [(5 + i, 10.0) for i in range(3)]
        s = janelas_p95(regs, 0, 10, 5)
        self.assertEqual(s["p95"], [10.0, None])
        self.assertEqual(s["n"], [30, 3])

    def test_estabilidade(self):
        def q(v):
            return json.dumps({"status": "success", "data": {"result": [{"value": [0, str(v)]}]}})
        cfg = {"CPU_REPOUSO_MAX_PCT": "25", "MEM_DISPONIVEL_MIN_GIB": "2", "DISCO_LIVRE_MIN_GIB": "20",
               "TEMP_MAX_C": "80"}
        ok = (f"cpu_max_pct\t{q(8)}\nmem_min_bytes\t{q(12 * 2**30)}\ntemp_max_c\t{q(55)}\n"
              f"alvos_min_up\t{q(1)}\ndisco_livre_bytes\t{300 * 2**30}\nestressores\tinactive inactive \n")
        est, motivos, _ = run_campaign.avaliar_estabilidade(ok, cfg)
        self.assertTrue(est, motivos)
        ruim = ok.replace(q(8), q(70)).replace("inactive inactive", "active inactive")
        est, motivos, _ = run_campaign.avaliar_estabilidade(ruim, cfg)
        self.assertFalse(est)
        self.assertEqual(len(motivos), 2)
        est, motivos, _ = run_campaign.avaliar_estabilidade("", cfg)  # Prometheus fora do ar
        self.assertFalse(est)

    def test_ler_env_com_comentario_na_linha(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.env"
            f.write_text('A=25   # PILOTO\nB="C0 C2"\nC=\n', encoding="utf-8")
            self.assertEqual(run_campaign.ler_env(str(f)), {"A": "25", "B": "C0 C2", "C": ""})

    def test_campanha_sem_c1(self):
        cfg = run_campaign.ler_env(str(ROOT / "experiments/scenarios/campaign.env"))
        blocos = [cfg[f"BLOCO_{b}"].split() for b in (1, 2, 3)]
        self.assertTrue(all(len(b) == 6 and "C1" not in b for b in blocos))
        self.assertFalse((ROOT / "experiments/scenarios/C1.env").exists())


class ExecutorCampanha(unittest.TestCase):
    """Executa o laco real do run_campaign.py com um run_scenario.sh FALSO."""

    FALSO = textwrap.dedent("""\
        #!/usr/bin/env bash
        # executor falso: cria a pasta da execucao como o run_scenario.sh faria
        set -eu
        n=$(ls -d "$RUNS_DIR/campaign/$1-$2-"* 2>/dev/null | wc -l)
        out="$RUNS_DIR/campaign/$1-$2-$(printf '%02d' "$n")"
        mkdir -p "$out"
        echo "- Classificacao final: PENDENTE" > "$out/notes.md"
        if [ "$1-$2" = "$FALHA" ] && [ "$n" -eq 0 ]; then echo "INVALIDA: falha tecnica" >> "$out/notes.md"; fi
        if [ "$1-$2" = "$ABORTA" ]; then exit 1; fi
        echo "executado $1 $2"
        """)

    def preparar(self, d: Path, falha="C2-r01", aborta="nenhum"):
        (d / "scenarios").mkdir()
        for c in ("C0", "C2", "C3"):
            (d / "scenarios" / f"{c}.env").write_text("INTERVENTION=none\n")
        (d / "scenarios" / "campaign.env").write_text(
            'BLOCO_1="C0 C2 C3"\nBLOCO_2="C3 C0 C2"\nINTERVALO_S=0\nREFAZER_FALHAS=1\n')
        (d / "common.env").write_text(f"RUNS_DIR={d / 'runs'}\nWARMUP_S=1\nPHASE_S=1\nSERVER=x@y\n")
        exe = d / "falso.sh"
        exe.write_text(self.FALSO)
        exe.chmod(0o755)
        env = {**os.environ, "RUNS_DIR": str(d / "runs"), "FALHA": falha, "ABORTA": aborta}
        cmd = [sys.executable, str(ROOT / "scripts/run_campaign.py"), "--config", str(d / "scenarios/campaign.env"),
               "--common", str(d / "common.env"), "--blocos", "1,2", "--sem-servidor", "--executor", str(exe)]
        return cmd, env

    def test_campanha_refaz_falha_e_retoma(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            cmd, env = self.preparar(d)
            p = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            pastas = sorted(x.name for x in (d / "runs" / "campaign").iterdir())
            # 6 execucoes + 1 nova tentativa de C2-r01 (a invalida e preservada)
            self.assertEqual(len(pastas), 7)
            self.assertIn("C2-r01-00", pastas)
            self.assertIn("C2-r01-01", pastas)
            p = subprocess.run(cmd, capture_output=True, text=True, env=env)  # retomada: nada novo
            self.assertEqual(p.returncode, 0)
            self.assertEqual(len(list((d / "runs" / "campaign").iterdir())), 7)
            self.assertIn("ja executada", p.stdout)

    def test_aborto_para_a_campanha_e_arquivo_parar(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            cmd, env = self.preparar(d, falha="nenhum", aborta="C2-r01")
            p = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 4)
            self.assertEqual(len(list((d / "runs" / "campaign").iterdir())), 2)  # C0 ok, C2 abortou
            (d / "runs" / "campaign-logs" / "PARAR").write_text("")
            env["ABORTA"] = "nenhum"
            p = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0)
            self.assertIn("PARAR", p.stdout)
            self.assertEqual(len(list((d / "runs" / "campaign").iterdir())), 2)

    def test_dry_run_sem_servidor(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            cmd, env = self.preparar(d)
            p = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("execucoes a fazer: 6", p.stdout)
            self.assertFalse((d / "runs" / "campaign").exists())


if __name__ == "__main__":
    unittest.main()
