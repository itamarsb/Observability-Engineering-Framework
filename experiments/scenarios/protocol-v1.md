# Protocolo experimental - versao v1 (CONGELADO em ____/____/2026, commit ________)

Preencha TODOS os campos antes da 1a execucao definitiva. Mudou algo? Crie protocol-v2.md,
registre o motivo e repita os cenarios afetados. Nao altere metas depois de ver resultados.

| Campo | Decisao registrada |
|---|---|
| Aplicacao | commit ____; imagem tcc2-api:____ (ID ____); n = 20000; digest esperado ____; 1 worker Uvicorn |
| Telemetria | Collector 0.162.0; Prometheus v3.15.0; Loki 3.7.8; Tempo 3.1.0; Grafana 13.1.3; digests em versions.txt; amostragem 100%; scrape 5 s; export de metricas 5 s; buckets ____; retencao 90 d |
| Gerador | notebook ____; WSL ____ (modo de rede NAT/espelhado); k6 v____; constant-arrival-rate; timeout 2 s; sem retries |
| Capacidade (rampa) | joelho em ____ RPS (P95 ____ ms no 1o degrau) |
| Demandas | C0 = R0 = ____ RPS; C2 = ____ RPS; C3 = ____ RPS; C4-C7 = R0 (C1 retirado do escopo) |
| Janelas | aquecimento 60 s; fase 180 s; C4-C6: antes/durante/depois de 180 s; atribuicao pelo horario de conclusao |
| Perturbacoes | C4: stress-ng --cpu 0 --cpu-load ____; C5: --vm 1 --vm-bytes ____ MemoryMax ____; C6: netem delay ____ ms na eth0 do NGINX; C7 (opcional): API parada 60 s |
| Sonda | /work a cada 5 s; timeout 2 s; sucesso = 200 + digest; cobertura minima 100% |
| Analise | posto mais proximo; populacao do SLI de latencia = respostas corretas; erro composto; Delta P95; recuperacao (30 s / 1,2x / 60 s) |
| Validade | aplicados por scripts/revisar_execucoes.py com os limites de validade.env. Carga: k6 com codigo 0, dropped_iterations = 0 e CPU do gerador <= 85%; sonda: cobertura 100%; telemetria: exportacao sem erro, series de CPU e memoria com amostras, nenhum conteiner reiniciado ou com OOMKilled; intervencao (C4-C7): inicio e fim registrados pelo servidor e codigo 0; integridade: checksums.sha256 conferido. Falha tecnica = INVALIDA; dropped > 0 ou CPU do gerador acima do limite = inconclusiva (decisao do operador, registrada no notes.md) |
| Metas (SLO) | P95 <= ____ ms; P99 <= ____ ms (regra: 2x piloto C0, multiplo de 25 ms); erro <= 1%; disponibilidade >= 99%; vazao com sucesso >= 95% da oferecida; aplicadas a fase util (C0, C2, C3) e a fase durante (C4-C7) |
| Ordem | bloco 1: C0 C2 C3 C4 C5 C6; bloco 2: C2 C4 C6 C3 C0 C5; bloco 3: C5 C3 C6 C0 C2 C4; intervalo >= 2 min + 60 s estavel (campaign.env) |
| Seguranca | MemAvailable >= 2 GiB; disco livre >= 20 GiB; temperatura < ____ C; abortar e registrar |
