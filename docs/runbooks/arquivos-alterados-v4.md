# Arquivos revisados para o pré-piloto — v4

Este registro identifica os arquivos propostos no [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1) em relação à branch `main` na abertura da revisão: **12 modificados e 4 adicionados**. O histórico do PR contém os detalhes por commit. Os testes de integração no Mini PC continuam pendentes.

## Aplicação e coleta

| Caminho | Alteração |
|---|---|
| `scripts/analyze_run.py` | Leitura dos registros JSON exportados pelo k6 |
| `scripts/run_scenario.sh` | Conferência do estado do Git e classificação de falhas técnicas |
| `scripts/export_run.py` | Exportação de logs e traces, incluindo metadados do Loki e tratamento de erros |
| `scripts/consolidate.py` | Inclusão apenas de execuções aprovadas e detecção de repetições duplicadas |
| `scripts/backup_volumes.sh` | Tratamento de interrupções, religação dos serviços e integridade dos arquivos |
| `tests/test_pipeline_offline.py` | Testes com dados sintéticos para análise e consolidação **(novo)** |

## Infraestrutura e documentação

| Caminho | Alteração |
|---|---|
| `.env.example` | Parâmetros da rede Docker para implantação isolada |
| `compose.yaml` | Configuração da rede e IP da API por variáveis |
| `.gitignore` | Exclusões de artefatos temporários e arquivos sensíveis |
| `README.md` | Ajustes de estado e limitações da infraestrutura |
| `docs/architecture/README.md` | Revisão da descrição da exposição de serviços |
| `docs/runbooks/deployment.md` | Procedimento de reimplantação isolada |
| `results/README.md` | Aprovação de execuções antes da consolidação |
| `docs/runbooks/verificacao-v4.md` | Checklist de verificação pré-piloto **(novo)** |
| `docs/runbooks/auditoria-repositorio-2026-10-20.md` | Auditoria técnica e limites da validação **(novo)** |
| `docs/runbooks/arquivos-alterados-v4.md` | Este inventário de alterações **(novo)** |

As alterações foram verificadas por leitura, validação sintática e testes offline. A aprovação do protocolo experimental depende dos testes reais previstos nos runbooks.
