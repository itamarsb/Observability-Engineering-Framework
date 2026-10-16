#!/usr/bin/env python3
"""Calcula, FORA do servidor, o digest esperado de GET /work?n=N.

Algoritmo identico ao da API: value = b"tcc2"; repetir N vezes sha256; imprimir hex.
Uso: python3 scripts/expected_digest.py 20000
"""
import hashlib
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
value = b"tcc2"
for _ in range(n):
    value = hashlib.sha256(value).digest()
print(value.hex())
