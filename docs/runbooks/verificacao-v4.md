# Verificação pré-piloto — revisão v4

Este roteiro reúne as correções submetidas no [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1) e as verificações necessárias antes da campanha definitiva. Os testes sintáticos e com dados sintéticos foram executados na preparação da revisão. **A integração no Mini PC ainda não foi testada.**

## Alterações a conferir

- `run_scenario.sh`: verificar o estado do Git nas duas máquinas e marcar falhas de k6, intervenção, exportação, cópia e análise como execuções inválidas.
- `export_run.py`: conferir a exportação de `structured_metadata` do Loki, o tratamento de respostas de erro e a sinalização de paginação incompleta.
- `analyze_run.py`: confirmar a interpretação dos registros JSON do k6 e a consistência com a consolidação.
- `consolidate.py`: aceitar apenas execuções aprovadas em `notes.md` e bloquear repetições duplicadas.
- `backup_volumes.sh`: conferir os volumes esperados, as somas SHA-256 e a religação dos serviços após uma interrupção.
- `compose.yaml` e `.env.example`: validar a parametrização da rede e do IP interno da API, inclusive no ambiente de reimplantação.

## Verificações obrigatórias antes da Etapa 8

1. Registrar as versões, tags e digests das imagens; executar `docker compose config` no Mini PC.
2. Examinar a porta 9100 do Node Exporter e as regras de firewall. Restringir o acesso antes de usar redes de terceiros, sem interromper a coleta do Prometheus.
3. Confirmar as Etapas 4A e 4B com métricas, logs e traces de uma mesma requisição, inclusive os metadados de correlação.
4. Testar as consultas do painel 01 com os rótulos efetivamente exportados (`job`, `http_route` e `le`).
5. Executar k6, sonda e perturbações somente em pilotos acompanhados, verificando a remoção dos estressores.
6. Conferir o backup, os hashes e uma restauração em volume de teste, sem alterar dados da campanha.
7. Testar a reimplantação em uma sub-rede distinta (proposta: `172.31.0.0/24`), sem colisão com a infraestrutura original.
8. Registrar as cargas, os critérios de validade e recuperação e as metas do protocolo antes da campanha definitiva.

## Critérios de análise

A latência considera respostas corretas; os erros são contabilizados separadamente. Cada cenário exige três repetições válidas, e os pilotos não entram nos resultados definitivos. A rotina automática identifica algumas falhas técnicas; a avaliação de `dropped_iterations`, taxa de carga efetiva, cobertura da sonda e coerência do estresse aplicado deve constar em `notes.md`.

Em caso de evidência insuficiente, mantenha a classificação `PENDENTE`. Registre o motivo de `INVALIDA` antes de repetir um ensaio. Nenhum cenário está homologado para a campanha apenas por passar nos testes offline.
