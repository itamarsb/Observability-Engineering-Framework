# Matriz experimental

**Situação:** rascunho. Demandas, intensidades e metas são calibradas nos pilotos e congeladas em [`scenarios/protocol-v1.md`](scenarios/protocol-v1.md) antes da campanha. Os valores aproximados abaixo são pontos de partida, e não resultados.

## Condições comuns

| Item | Definição |
|---|---|
| Operação | `GET /work?n=20000` por meio do NGINX (porta 8080) |
| Sucesso | HTTP 200 **e** `n` e `digest` corretos no corpo da resposta |
| Modelo de carga | k6 `constant-arrival-rate`, uma requisição por iteração, timeout de 2 s, sem novas tentativas e sem redirecionamentos |
| Gerador de carga | Notebook (WSL2), fora do servidor, pela rede cabeada dedicada |
| Sonda externa | `GET /work` a cada 5 s, timeout de 2 s, independente do k6 |
| Janelas | 60 s de aquecimento + 180 s de fase útil; C4–C6: 180 s *antes*, *durante* e *depois*; C7: 180 s *antes*, 60 s com a API parada, 180 s *depois* |
| Atribuição às fases | Pelo horário de conclusão da requisição |
| Repetições | 3 execuções válidas por cenário, em 3 blocos com ordem alternada |
| Intervalo entre execuções | No mínimo 2 min, mais 60 s de estado estável |
| Relógio | Servidor em UTC (chrony); deslocamento entre notebook e servidor medido em toda execução (limite: 1 s) |
| Identificação | `run_id = <cenário>-<repetição>-<horário UTC>`, enviado no cabeçalho `X-Run-ID` |

## Cenários

| ID | Cenário | Demanda | Perturbação | Script / parâmetros |
|---|---|---|---|---|
| C0 | Referência (baseline) | R0 ≈ 20–25% da capacidade | Nenhuma | [`C0.env`](scenarios/C0.env) |
| C1 | Baixa carga | ≈ 5–10% da capacidade | Nenhuma | [`C1.env`](scenarios/C1.env) |
| C2 | Média carga | ≈ 40–50% da capacidade | Nenhuma | [`C2.env`](scenarios/C2.env) |
| C3 | Alta carga | ≈ 70–80% da capacidade | Nenhuma | [`C3.env`](scenarios/C3.env) |
| C4 | Contenção de CPU | R0 | `stress-ng --cpu 0 --cpu-load <piloto>` no host inteiro | [`tcc2-cpu.sh`](stress-ng/tcc2-cpu.sh) |
| C5 | Pressão de memória | R0 | `stress-ng --vm 1` sob `MemoryMax`, sem swap para a unidade | [`tcc2-mem.sh`](stress-ng/tcc2-mem.sh) |
| C6 | Atraso de rede | R0 | `tc netem delay` na `eth0` do contêiner do NGINX | [`tcc2-net.sh`](stress-ng/tcc2-net.sh) |
| C7 | Falha controlada da API (opcional) | R0 | Contêiner da API parado por 60 s e depois reiniciado | [`tcc2-apifail.sh`](stress-ng/tcc2-apifail.sh) |

A capacidade é medida antes, com uma rampa em degraus ([`k6/ramp.js`](k6/ramp.js), degraus de 60 s). O *joelho* é o primeiro degrau em que a latência P95 dobra em relação ao primeiro degrau, surgem falhas ou `dropped_iterations > 0`.

O início e o fim das perturbações são registrados pelo próprio servidor e alinhados aos dados do cliente com o deslocamento de relógio medido.

## Ordem dos blocos

| Bloco | Ordem |
|---|---|
| 1 | C0, C1, C2, C3, C4, C5, C6 |
| 2 | C2, C4, C6, C1, C3, C0, C5 |
| 3 | C5, C3, C1, C6, C0, C2, C4 |

O C7, se mantido, é executado ao final de cada bloco, porque reinicia a API.

## Indicadores por execução

- Latência P95 e P99 das respostas corretas (método do posto mais próximo).
- Taxa de erro composta (status ≠ 200, corpo incorreto, timeout ou erro de conexão).
- Vazão com sucesso e vazão observada.
- Disponibilidade amostrada pela sonda externa (somente quando a cobertura da sonda é de 100%).
- Para C4–C7: variação do P95 em relação à fase *antes* e tempo de recuperação — primeira janela de 30 s com P95 ≤ 1,2 × o P95 da fase *antes* e sem falhas, mantida por 60 s.
- Contexto de recursos: CPU do host, memória disponível, tráfego de rede e temperatura; itens aceitos, recusados e enfileirados pelo Collector.

## Limites de segurança

- Memória disponível mantida em pelo menos 2 GiB; disco livre em pelo menos 20 GiB.
- Temperatura máxima definida após os pilotos.
- Uma execução que ultrapassar um limite é abortada, mantida e marcada como inválida.
