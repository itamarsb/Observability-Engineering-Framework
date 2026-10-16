# Implantacao do framework (runbook) - TCC2

Este roteiro e o usado na Etapa 10 (reimplantacao). Anote TODO passo que precisar de
intervencao manual nao descrita aqui: isso e resultado da secao 4.8 do artigo.

## Pre-requisitos no servidor
- Ubuntu Server 26.04 LTS atualizado; Docker Engine + plugin Compose (repositorio oficial).
- Usuario `itamar` nos grupos `docker` e `adm`.
- Rede dedicada: `enp2s0` com 10.10.10.1/24 (netplan 60-lab.yaml).
- Pacotes: git curl jq chrony stress-ng lm-sensors iproute2 util-linux python3.

## Passos
1. `git clone https://github.com/itamarsb/Observability-Engineering-Framework.git`
2. `cd Observability-Engineering-Framework && git checkout <tag-ou-commit-da-campanha>`
3. `cp .env.example .env` e preencher GRAFANA_ADMIN_PASSWORD, APP_VERSION, LAB_BIND_IP.
4. `docker compose config -q` (sem saida = valido).
5. `docker compose build api`
6. `docker compose up -d api nginx` e testes funcionais (health, work, parametro invalido).
7. `docker compose up -d prometheus loki tempo grafana`
8. `docker compose up -d collector node-exporter`
9. `docker compose ps` (todos "running"/"healthy") e prova de correlacao (Etapa 4B).
10. `sudo bash scripts/install_server_scripts.sh itamar` (intervencoes + sudoers).

## Reimplantacao isolada (Etapa 10)
`docker compose -p tcc2-repro up -d` em um clone novo, com a stack original parada.
Atencao: os scripts de intervencao usam PROJECT=tcc2 por padrao; para o projeto
de reproducao use `sudo PROJECT=tcc2-repro ...` apenas se for testar intervencoes.

## Remover manualmente o atraso de rede (netem)
Se o script do cenario C6 for interrompido antes da limpeza, remova a regra da eth0 do
conteiner NGINX e confira com `tc qdisc show` que ela sumiu:

```bash
sudo bash -c 'PID=$(docker inspect -f "{{.State.Pid}}" $(docker ps -q --filter label=com.docker.compose.project=tcc2 --filter label=com.docker.compose.service=nginx)); nsenter -t "$PID" -n tc qdisc del dev eth0 root; nsenter -t "$PID" -n tc qdisc show dev eth0'
```

## Desligar sem perder dados
`docker compose stop` (NUNCA `docker compose down -v`, que apaga os volumes).
