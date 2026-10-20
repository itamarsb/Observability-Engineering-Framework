# Kit v4 (revisao estatica) - lista de verificacao antes do piloto

Este ZIP preserva o projeto original e aplica correcoes locais verificadas por leitura,
validacao sintatica e testes isolados. NAO foi executado no Mini PC e nao tem homologacao
end-to-end com Grafana/NGINX/k6/OTLP.

## Correcoes incorporadas
- `run_scenario.sh`: bloqueia campanha com arquivos Git nao rastreados (notebook e servidor);
  marca automaticamente como INVALIDA se k6, intervencao, exportacao, copia, analise ou
  `export-report.json` falharem.
- `export_run.py`: grava `structured_metadata` dos registros Loki, incluindo possivel `trace_id`;
  rejeita respostas de API `status=error`; falhas exportadas passam a retornar codigo nao zero;
  interrompe paginacao Loki com carimbo de tempo ambiguo para nao ocultar possivel perda.
- `analyze_run.py`: interpreta registros JSON do k6 com parser JSON, sem depender da ausencia de espacos;
  teste sintetico confirmou o caminho do dado ao `consolidate.py`.
- `backup_volumes.sh`: reinicia servicos mesmo diante de falhas/interrupcao; exige volumes presentes,
  confere hashes dos `.tgz`.
- `compose.yaml`/`.env.example`: sub-rede Docker e IP interno da API parametrizaveis;
  a reimplantacao usa faixa distinta e fica documentada no runbook.

## Bloqueios pendentes no equipamento (NAO liberar Etapa 8)
1. Verificar versoes/tag/digest das imagens e `docker compose config` no Mini PC.
2. Verificar Node Exporter na rede host: porta 9100 pode ficar exposta nas interfaces
   fisicas. Antes de ligar a rede a terceiros, restringir acesso e documentar a medida;
   nao mudar bind sem conferir o scrape Prometheus.
3. Testar 4A/4B: traces, metricas e logs do mesmo evento; verificar `structured_metadata`.
4. Testar painel 01 PromQL com labels REAIS; confirmar `job`, `http_route`, `le`.
5. Testar k6/probe e scripts de perturbacao APENAS durante pilotos supervisionados.
6. Testar backup, verificar hashes e RESTAURAR num diretorio/volume de teste.
7. Testar reimplantacao em 172.31.0.0/24, sem colidir com a stack original.
8. Congelar protocolo, parametros, validade e criterios de recuperacao antes da campanha.

## Atenção metodologica
A analise mantem os criterios originais de latencia nas respostas corretas,
falha composta separada, 3 repeticoes, pilotos excluidos dos resultados finais.
A rotina automatica so cobre invalidacoes TECNICAS; dropped_iterations, taxa real,
cobertura da sonda e coerencia do recurso devem ser revisados e registrados em `notes.md`.

Esta versao e uma proposta de codigo para ensaio/piloto. Antes de adotar, compare com
`git diff --no-index` e registre as alteracoes no repositorio em commits pequenos.
