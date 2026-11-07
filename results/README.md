# Resultados

Nenhum resultado experimental foi publicado até o momento. Os pilotos servem apenas para calibrar parâmetros e não são apresentados como resultados.

## Organização dos dados

| Local | Conteúdo | Versionado |
|---|---|---|
| `runs/pilot/`, `runs/campaign/` | Uma pasta por execução (`<cenário>-<repetição>-<horário UTC>`): manifesto, saída bruta do k6, dados da sonda, eventos do servidor, exportações do Prometheus, do Loki e do Tempo, logs dos contêineres e `checksums.sha256` | Não — mantidos fora do Git, em três cópias |
| [`processed/`](processed/) | Resumos consolidados (`summary-*.csv`) gerados a partir das execuções analisadas | Somente os resumos |
| [`charts/`](charts/) | Figuras geradas pelos scripts de gráficos | Não — regeneradas a partir dos dados |
| [`evidence-index.csv`](evidence-index.csv) | Índice de rastreabilidade: cada evidência, o arquivo de origem, o script ou a consulta que a produziu e onde é utilizada | Sim |

Execuções abortadas, inválidas ou **ainda não avaliadas** são preservadas e ficam fora da consolidação. A classificação de cada execução fica em `notes.md`, na linha `- Classificacao final: VALIDA`, `INVALIDA` ou `PENDENTE`; só as execuções `VALIDA` entram nos resultados.

## Fluxo de trabalho (automatizado)

```bash
# Etapa 6 — calibração
scripts/run_ramp.sh                                   # rampa de capacidade + Figura C10
python3 scripts/calibrar_taxas.py --aplicar           # taxas de C0, C2, C3 (e R0 para C4–C7) a partir da rampa
scripts/run_scenario.sh C0 r01 pilot                  # pilotos C0 (r01, r02, r03)
python3 scripts/derive_slo.py runs/pilot --gravar     # metas P95/P99 -> slo.env e protocol-v1.md

# Etapa 8 — campanha (3 blocos × 6 cenários = 18 execuções)
python3 scripts/run_campaign.py --dry-run             # plano, duração estimada e verificação do servidor
python3 scripts/run_campaign.py                       # executa (ou retoma)

# Etapa 9 — revisão e resultados
python3 scripts/revisar_execucoes.py                  # propõe VALIDA / INVALIDA / INCONCLUSIVA
python3 scripts/revisar_execucoes.py --aplicar        # grava nos notes.md (com confirmação)
python3 scripts/gerar_resultados.py                   # consolida, gera as figuras e as tabelas
```

**Calibração.** O `calibrar_taxas.py` define a capacidade (Cap) como o maior degrau estável antes do joelho e propõe C0 = R0 = 22,5% de Cap, C2 = 45% e C3 = 75% (meio das faixas da [matriz experimental](../experiments/experimental-matrix.md)); os cenários com perturbação usam R0. Ele avisa quando a CPU do gerador indica que o limite medido pode ser do notebook. O `derive_slo.py --gravar` aplica a regra das metas (2 × mediana dos pilotos C0, arredondada para cima em múltiplos de 25 ms). Os dois scripts gravam também as linhas correspondentes do [`protocol-v1.md`](../experiments/scenarios/protocol-v1.md) e se recusam a alterar qualquer coisa depois do congelamento (`PROTOCOL_VERSION` sem `-rascunho`).

**Campanha.** O executor chama `scripts/run_scenario.sh` uma vez por execução, respeita o intervalo mínimo e confere o estado estável do servidor antes de cada execução (CPU em repouso, memória disponível, disco, temperatura, alvos do Prometheus e estressores parados), conforme [`campaign.env`](../experiments/scenarios/campaign.env). Uma execução invalidada automaticamente por falha técnica é preservada e refeita no fim do bloco; um aborto por pré-condição ou `Ctrl+C` interrompe a campanha. Para parar com segurança ao fim da execução atual, crie o arquivo `runs/campaign-logs/PARAR`. Para retomar, execute o mesmo comando.

**Revisão.** O `revisar_execucoes.py` aplica os critérios da linha *Validade* do protocolo, com os limites de [`validade.env`](../experiments/scenarios/validade.env): carga (k6, `dropped_iterations`, CPU do gerador), sonda (cobertura), telemetria (exportação, séries, reinícios e OOM), intervenção (eventos e código de retorno) e integridade (`checksums.sha256`). Falha técnica resulta em `INVALIDA`; casos que exigem julgamento (por exemplo, `dropped_iterations > 0`) ficam `INCONCLUSIVA`, continuam `PENDENTE` e recebem os motivos no `notes.md` para a decisão do operador. Cada revisão grava um relatório em `runs/campaign-logs/`.

**Resultados.** O `gerar_resultados.py` consolida as execuções válidas, escolhe para C4, C5 e C6 a execução de ΔP95 mediano, gera a Figura 3, a Figura 4, as Figuras C10, C12, C13 e C14 e as Tabelas 2 e 3, o Quadro 3 e as Tabelas A1–A3, e grava `results/resultados-<UTC>.md` com o commit, as escolhas, os avisos e o SHA-256 de cada arquivo. Com `--copiar-para <pasta>`, copia tudo para uma pasta do Windows. Os scripts individuais (`fig_carga.py`, `fig_perturbacao.py`, `fig_rampa.py`, `tabelas_artigo.py`) continuam disponíveis para gerar uma figura isolada.

Cada figura grava ao lado um arquivo `<figura>.png.fonte.json` com o script, os parâmetros e o SHA-256 de todas as entradas lidas. Valores sem amostras válidas aparecem como `indef.`, nunca como zero, e o Quadro 3 só emite veredito de latência depois que as metas estiverem em [`slo.env`](../experiments/scenarios/slo.env).

A integridade da pasta de uma execução pode ser conferida com `sha256sum -c checksums.sha256`, executado dentro da pasta.

## Testes offline

```bash
python3 -m unittest discover -s tests -v
```

Os testes usam execuções **sintéticas** geradas por [`tests/synthetic_runs.py`](../tests/synthetic_runs.py), no mesmo formato da bancada, para verificar revisão, calibração, análise, figuras, tabelas, a geração de resultados e o executor da campanha sem Docker, k6 ou servidor. Dados sintéticos são marcados no manifesto (`"synthetic": true`) e saem sempre com marca d'água nas figuras e prefixo `SINTETICO_` nas tabelas; não existe opção para remover essa marcação.
