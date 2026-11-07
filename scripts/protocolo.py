"""Utilitarios para ler e gravar os arquivos de configuracao do protocolo (biblioteca padrao).

  ler_env / gravar_env       arquivos KEY=valor (common.env, C*.env, slo.env, validade.env)
  definir_linha_protocolo    troca o texto de uma linha da tabela de protocol-v1.md
  protocolo_congelado        True se PROTOCOL_VERSION nao termina em "-rascunho"
  confirmar                  pergunta s/N no terminal (ou aceita direto com --sim)
Regra de seguranca: depois do congelamento (PROTOCOL_VERSION=v1), nenhum script altera
taxas, metas ou o protocolo; mudancas exigem protocol-v2.md (ver protocol-v1.md).
"""

from __future__ import annotations

import os
import re
import sys

CENARIOS_DIR = "experiments/scenarios"
PROTOCOLO = os.path.join(CENARIOS_DIR, "protocol-v1.md")
COMMON = os.path.join(CENARIOS_DIR, "common.env")


def ler_env(caminho: str) -> dict:
    out = {}
    if not os.path.exists(caminho):
        return out
    with open(caminho, encoding="utf-8") as fh:
        linhas = fh.readlines()
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip()
        if v.startswith('"'):
            v = v[1:v.index('"', 1)] if '"' in v[1:] else v[1:]
        else:
            v = v.split("#", 1)[0].strip()
        out[k.strip()] = v
    return out


def gravar_env(caminho: str, chave: str, valor: str) -> None:
    """Troca a linha CHAVE=... (mantem comentarios e demais linhas); acrescenta se nao existir."""
    with open(caminho, encoding="utf-8") as fh:
        linhas = fh.readlines()
    padrao = re.compile(rf"^\s*{re.escape(chave)}\s*=")
    feito = False
    for i, li in enumerate(linhas):
        if padrao.match(li):
            linhas[i] = f"{chave}={valor}\n"
            feito = True
            break
    if not feito:
        if linhas and not linhas[-1].endswith("\n"):
            linhas[-1] += "\n"
        linhas.append(f"{chave}={valor}\n")
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.writelines(linhas)


def definir_linha_protocolo(caminho: str, campo: str, texto: str) -> None:
    """Na tabela Markdown do protocolo, substitui o conteudo da linha '| campo | ... |'."""
    with open(caminho, encoding="utf-8") as fh:
        linhas = fh.readlines()
    for i, li in enumerate(linhas):
        partes = li.split("|")
        if len(partes) >= 4 and partes[1].strip() == campo:
            linhas[i] = f"| {campo} | {texto} |\n"
            with open(caminho, "w", encoding="utf-8") as fh:
                fh.writelines(linhas)
            return
    raise KeyError(f"linha '{campo}' nao encontrada em {caminho}")


def linha_protocolo(caminho: str, campo: str) -> str | None:
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as fh:
        for li in fh:
            partes = li.split("|")
            if len(partes) >= 4 and partes[1].strip() == campo:
                return "|".join(partes[2:-1]).strip()
    return None


def protocolo_congelado(common_env: str = COMMON) -> bool:
    versao = ler_env(common_env).get("PROTOCOL_VERSION", "")
    return bool(versao) and not versao.endswith("-rascunho")


def confirmar(pergunta: str, sim: bool) -> bool:
    if sim:
        return True
    if not sys.stdin.isatty():
        print("sem terminal interativo: use --sim para confirmar sem perguntar")
        return False
    return input(f"{pergunta} [s/N] ").strip().lower() in ("s", "sim", "y")
