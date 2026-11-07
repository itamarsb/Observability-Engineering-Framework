"""Estilo comum das figuras do artigo e dos apendices (TCC2).

- Tamanho real de impressao: largura padrao de 15,5 cm (corpo do artigo).
- Tema claro, virgula decimal, PNG 300 dpi, eixos a partir de zero quando fizer sentido.
- Sem titulo dentro da imagem: a legenda "Figura N - ..." fica no documento.
- Marca d'agua OBRIGATORIA quando qualquer entrada for sintetica (teste do pipeline).
  Nao existe opcao para desligar a marca: dado sintetico nunca vira evidencia.
- Cada figura gera <saida>.fonte.json com scripts, parametros e SHA-256 das entradas
  (rastreabilidade exigida no Apendice B.1).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

LARGURA_CM = 15.5
DPI = 300

# Paleta (a mesma dos modelos visuais do rascunho)
COR = {
    "p95": "#1f6f8b",
    "p99": "#b5652a",
    "vazao": "#1b7a72",
    "oferta": "#6b7785",
    "cpu": "#b5652a",
    "cpu_gerador": "#8a5a9e",
    "interno": "#5b4a9b",
    "mem": "#2e7d5b",
    "swap": "#b5652a",
    "erro": "#c98a4b",
    "dropped": "#b0475b",
    "titulo": "#17465c",
    "eixo": "#5f6b75",
    "grade": "#e3e6e9",
    "evento": "#b5652a",
    "limite": "#b0475b",
}
FASES = {
    # fase: (cor de fundo, cor do rotulo, rotulo)
    "aquecimento": ("#f4f5f6", "#7a848c", "AQUEC."),
    "antes": ("#e8f3ee", "#2e6b4f", "ANTES"),
    "durante": ("#fbeee3", "#a35d1c", "DURANTE"),
    "depois": ("#e9f1f9", "#3f6687", "DEPOIS"),
    "util": ("#eef4f7", "#3f6687", "FASE ÚTIL"),
}
TEXTO_SINTETICO = "DADOS SINTÉTICOS — TESTE DO PIPELINE — NÃO É EVIDÊNCIA"


def aplicar_estilo(base_pt: float = 7.5) -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": base_pt,
        "axes.titlesize": base_pt + 0.5,
        "axes.labelsize": base_pt,
        "xtick.labelsize": base_pt - 0.5,
        "ytick.labelsize": base_pt - 0.5,
        "legend.fontsize": base_pt - 0.5,
        "axes.edgecolor": COR["eixo"],
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": COR["grade"],
        "grid.linewidth": 0.5,
        "xtick.color": "#333333",
        "ytick.color": "#333333",
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "lines.linewidth": 1.3,
        "legend.frameon": False,
        "savefig.facecolor": "white",
    })


def cm(largura: float, altura: float) -> tuple[float, float]:
    return largura / 2.54, altura / 2.54


def num_br(v: float, casas: int | None = None) -> str:
    """Numero com virgula decimal (sem separador de milhar)."""
    if v is None:
        return "indef."
    txt = f"{v:g}" if casas is None else f"{v:.{casas}f}"
    return txt.replace(".", ",")


virgula = FuncFormatter(lambda v, _p: num_br(round(v, 6)))


def formatar_eixos(axs, eixo_x: bool = False) -> None:
    """Virgula decimal no eixo y (e no x, quando numerico)."""
    for ax in axs:
        ax.yaxis.set_major_formatter(virgula)
        if eixo_x:
            ax.xaxis.set_major_formatter(virgula)


def marca_sintetica(fig) -> None:
    """Faixa no topo + texto diagonal. Chamada sempre que houver entrada sintetica."""
    fig.text(0.5, 0.5, "SINTÉTICO", fontsize=48, color="#b0475b", alpha=0.13,
             ha="center", va="center", rotation=20, weight="bold", zorder=100)
    fig.text(0.5, 0.995, TEXTO_SINTETICO, fontsize=7, color="white", weight="bold",
             ha="center", va="top", zorder=101,
             bbox={"boxstyle": "square,pad=0.25", "fc": "#b0475b", "ec": "none"})


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def salvar(fig, saida: str, script: str, entradas: list[str], parametros: dict,
           sintetico: bool) -> None:
    """Salva PNG 300 dpi e o registro de rastreabilidade <saida>.fonte.json."""
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    if sintetico:
        marca_sintetica(fig)
    fig.savefig(saida, dpi=DPI)
    plt.close(fig)
    fonte = {
        "figura": os.path.basename(saida),
        "gerado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "script": script,
        "parametros": parametros,
        "dados_sinteticos": sintetico,
        "entradas": [{"arquivo": e, "sha256": sha256_arquivo(e)} for e in sorted(set(entradas))
                     if os.path.isfile(e)],
        "sha256_png": sha256_arquivo(saida),
    }
    with open(saida + ".fonte.json", "w", encoding="utf-8") as fh:
        json.dump(fonte, fh, indent=2, ensure_ascii=False)
    aviso = "  [SINTETICO: marca d'agua aplicada]" if sintetico else ""
    print(f"figura salva em {saida} (rastreabilidade: {os.path.basename(saida)}.fonte.json){aviso}")


def rodape(fig, partes: list[str], altura_cm: float, colunas: int = 125) -> float:
    """Escreve o rodape (quebrado em linhas) e devolve a fracao inferior que ele ocupa."""
    linhas = textwrap.wrap(" • ".join(p for p in partes if p), colunas)
    fig.text(0.5, 0.004, "\n".join(linhas), ha="center", va="bottom", fontsize=5.6,
             color=COR["eixo"], linespacing=1.3)
    return (0.15 + 0.28 * len(linhas)) / altura_cm


def topo(altura_cm: float, sintetico: bool) -> float:
    """Fracao superior livre para a faixa de dados sinteticos."""
    return 1 - 0.45 / altura_cm if sintetico else 1


def faixas_de_fase(ax, fases: list[tuple[str, float, float]], rotulos: bool = False,
                   eventos: tuple[float | None, float | None] = (None, None)) -> None:
    """Sombreia as fases (tempo relativo, em s) e marca inicio/fim da intervencao."""
    for nome, a, b in fases:
        fundo, cor_rot, rot = FASES.get(nome, ("#ffffff", "#555555", nome.upper()))
        ax.axvspan(a, b, color=fundo, lw=0, zorder=0)
        if rotulos:
            ax.text((a + b) / 2, 0.97, rot, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=6.5, color=cor_rot, weight="bold")
    for t in eventos:
        if t is not None:
            ax.axvline(t, color=COR["evento"], ls="--", lw=0.9, zorder=2)
