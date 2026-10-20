# Auditoria do repositório e preparação dos pilotos — 20/10/2026

**Escopo.** Revisão do ZIP `Observability-Engineering-Framework-main(2).zip` comparado ao `TCC2_Kit_Laboratorio_v4_PrePiloto.zip` e ao Manual de Bancada v3.1. É uma revisão **do snapshot enviado**, não uma verificação do branch remoto do GitHub. Não houve commit, push, execução no Mini PC ou testes com Docker/NGINX/Grafana reais.

## Alterações técnicas incorporadas

| Prioridade | Local | Problema na cópia original | Tratamento no pacote revisado |
|---|---|---|---|
| Alta | `scripts/analyze_run.py` | Parser dependente da formatação textual do JSON do k6 | Importada correção do kit v4: interpretar o JSON e depois verificar o tipo do registro |
| Alta | `scripts/run_scenario.sh` | Checagem do Git ignorava arquivos não rastreados e algumas falhas não eram explicitamente marcadas | Importada correção v4 e acrescentado estado inicial `Classificacao final: PENDENTE` |
| Alta | `scripts/export_run.py` | Log do Loki não preservava metadados estruturados; erros de exportação não afetavam o retorno | Importada correção v4 e verificação adicional para traces do Tempo selecionados, mas não salvos |
| Alta | `scripts/consolidate.py` | Qualquer execução com `analysis/phases.csv` podia entrar no resumo se não houvesse texto `INVALIDA`, mesmo com validade pendente | Somente `Classificacao final: VALIDA` permite consolidação; recusa execuções duplicadas com mesma combinação cenário/repetição |
| Alta | `scripts/backup_volumes.sh` | Falha de backup podia deixar a stack parada e o projeto alvo era implícito | Importada correção v4, seleção explícita com `-p "$PROJECT"`, caminho absoluto e verificação SHA-256 |
| Média | `compose.yaml`, `.env.example` | Rede Docker/IP da API fixos dificultavam reimplantação isolada | Variáveis `LAB_DOCKER_SUBNET` e `API_IPV4`, com valores padrão existentes |
| Média | `docs/runbooks/deployment.md` | Reimplantação com segunda rede podia conflitar com rede original | Instrução de sub-rede isolada. A recuperação manual de `tc netem` foi preservada |
| Média | `README.md`, `docs/architecture/README.md` | Declaração de que apenas NGINX está exposto omitia o Node Exporter com `network_mode: host` | Documentada a exceção e a necessidade de verificar a porta 9100 |
| Média | `results/README.md` | Faltava explicar aprovação humana da execução antes dos resumos | Adicionada aprovação explícita e controles de duplicidade |
| Baixa | `.gitignore` | Proteções adicionais para artefatos locais não estavam descritas | Acrescentadas regras de exclusão preventivas, sem excluir evidências ou código já versionados |
| Média | `tests/test_pipeline_offline.py` | Não havia testes automatizados de regressão para o pipeline de análise | Criados testes unitários sintéticos com Python padrão, sem hardware e sem instalações |

O conteúdo de `app/`, a matriz de cenários, os painéis, as capturas de instalação e as referências acadêmicas foram preservados, exceto onde indicado. **Não substitua** o repositório pelo kit isolado: o kit não contém toda a documentação, histórico visual e arquivos adicionais presentes no ZIP.

## Atenção: validação ainda pendente no Mini PC

1. Validar as versões reais, `docker compose config -q`, saúde dos contêineres e dependências de Python e k6.
2. Inspecionar `ss -ltnp | grep ':9100'` e regras do firewall. O Node Exporter em rede do host pode tornar a porta acessível por outras interfaces. Não afirmar isolamento sem prova.
3. Comprovar a sequência API → OpenTelemetry Collector → Prometheus/Loki/Tempo e os UIDs dos painéis Grafana.
4. Verificar labels reais `job`, `http_route`, `le` e semântica das consultas PromQL na API e no painel 01.
5. Confirmar que o mesmo `trace_id` aparece no Loki, no Tempo e na exportação da execução.
6. Simular deliberadamente uma exportação incompleta e verificar que a execução é classificada como inválida.
7. Ensaiar backup, hash e restauração de teste, sem sobrescrever dados de campanha.
8. Executar C4–C7 apenas durante pilotos supervisionados, verificando a limpeza de estressores (`systemctl`, `tc`).
9. Inspecionar visualmente imagens e capturas públicas antes de criar novas postagens, para não divulgar segredos, usuários, endereço de rede global, tokens ou dados pessoais.
10. Congelar critérios de validade, cargas e SLOs no protocolo antes da Etapa 8 e registrar commit/tag das versões dos scripts e configurações.

**Limitações desta revisão.** A sintaxe é validada localmente, mas não podemos afirmar compatibilidade real das versões fixadas, volume das retenções, consumo de CPU/memória, comunicação entre contêineres, timeouts do k6 ou desempenho do Mini PC sem o laboratório. `run_scenario.sh` tem caminhos de exceção e ações privilegiadas que requerem pilotos supervisionados. Nenhum cenário da campanha está homologado por esta auditoria.

## Como testar as alterações em segurança

No clone local do repositório, execute os comandos de leitura/validação, sem subir a stack:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
find scripts -name '*.py' -print0 | xargs -0 -r -n1 python3 -m py_compile
bash -n scripts/run_scenario.sh scripts/backup_volumes.sh
```

Aprovação humana de execução (somente após conferir `notes.md`, dados brutos e relatório do exportador):

```text
- Classificacao final: VALIDA
```

Em caso de dúvida, mantenha `PENDENTE`; para execução inválida, use `INVALIDA` e descreva o motivo. **Não mude os critérios de validade durante a campanha.** O script de consolidação não decide sozinho se a carga e os recursos foram válidos.

## Aplicação no GitHub

Trabalhe em branch separado e faça commits curtos, por exemplo:

1. `fix: garantir integridade da coleta e analise` — scripts e testes.
2. `fix: parametrizar rede e proteger backup` — Compose, `.env.example`, runbooks.
3. `docs: atualizar criterios e pendencias dos pilotos` — documentação, `.gitignore`.

**Não faça push automático sem revisar o `git diff`**. O ZIP é um snapshot; mudanças posteriores no GitHub precisam ser reconciliadas antes de copiar arquivos por cima. Não envie `.env`, credenciais, `runs/` ou resultados brutos para o GitHub.
