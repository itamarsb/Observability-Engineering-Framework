# Resultados

Nenhum resultado experimental foi publicado até o momento. Os pilotos servem apenas para calibrar parâmetros e não são apresentados como resultados.

## Organização dos dados

| Local | Conteúdo | Versionado |
|---|---|---|
| `runs/pilot/`, `runs/campaign/` | Uma pasta por execução (`<cenário>-<repetição>-<horário UTC>`): manifesto, saída bruta do k6, dados da sonda, eventos do servidor, exportações do Prometheus, do Loki e do Tempo, logs dos contêineres e `checksums.sha256` | Não — mantidos fora do Git, em três cópias |
| [`processed/`](processed/) | Resumos consolidados (`summary-*.csv`) gerados a partir das execuções analisadas | Somente os resumos |
| [`charts/`](charts/) | Figuras geradas pelos scripts de gráficos | Não — regeneradas a partir dos dados |
| [`evidence-index.csv`](evidence-index.csv) | Índice de rastreabilidade: cada evidência, o arquivo de origem, o script ou a consulta que a produziu e onde é utilizada | Sim |

Execuções abortadas ou inválidas são preservadas e marcadas como tal; elas são listadas, mas ficam fora da consolidação.

## Processamento

```bash
python3 scripts/analyze_run.py runs/campaign/<run_id>          # indicadores por fase e por execução
python3 scripts/consolidate.py runs/campaign results/processed  # resumos consolidados
python3 scripts/plot_load.py results/processed/summary-runs.csv # figura de resposta à carga (C0–C3)
python3 scripts/plot_run.py runs/campaign/<run_id>              # série temporal de uma execução com perturbação (C4–C7)
```

A integridade da pasta de uma execução pode ser conferida com `sha256sum -c checksums.sha256`, executado dentro da pasta.
