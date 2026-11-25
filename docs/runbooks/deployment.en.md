# Framework Deployment Runbook — TCC2

**Language:** [Português (Brasil)](deployment.md) | **English (US)**

Step-by-step deployment procedure documented to enable independent reproduction.
Record every step that requires manual intervention not described here.

## Server prerequisites
- Up-to-date Ubuntu Server 26.04 LTS; Docker Engine and the Compose plugin (official repository).
- User `itamar` in the `docker` and `adm` groups.
- Dedicated network: `enp2s0` with 10.10.10.1/24 (Netplan 60-lab.yaml).
- Packages: git curl jq chrony stress-ng lm-sensors iproute2 util-linux python3.

## Deployment steps
1. `git clone https://github.com/itamarsb/Observability-Engineering-Framework.git`
2. `cd Observability-Engineering-Framework && git checkout <tag-ou-commit-da-campanha>`
3. `cp .env.example .env` and set GRAFANA_ADMIN_PASSWORD, APP_VERSION, and LAB_BIND_IP.
4. `docker compose config -q` (no output = valid configuration).
5. `docker compose build api`
6. `docker compose up -d api nginx` and run functional tests (health, work, invalid parameter).
7. `docker compose up -d prometheus loki tempo grafana`
8. `docker compose up -d collector node-exporter`
9. `docker compose ps` (all services "running"/"healthy") and verify correlation (Stage 4B).
10. `sudo bash scripts/install_server_scripts.sh itamar` (intervention scripts and sudoers configuration).

The placeholder `<tag-ou-commit-da-campanha>` denotes the campaign tag or commit. Replace it with the actual Git reference before executing step 2. The account name and network interface above reflect the documented lab environment; independent deployments must use their corresponding local values.

## Second isolated installation on the same server (optional, for independent reproduction)
In the new clone, use a separate `.env` with `LAB_DOCKER_SUBNET=172.31.0.0/24`
and `API_IPV4=172.31.0.10` (or another available address range verified in Docker),
because `docker compose stop` does not remove the original 172.30.0.0/24 network.
The original stack must remain stopped to free the host ports
(8080/3000/9090/3100/3200/9100). Do not run scenarios against both stacks.
Run `docker compose -p tcc2-repro config -q` to validate the configuration before starting.
Run `docker compose -p tcc2-repro up -d` in the new clone while the original stack remains stopped.
Note: the intervention scripts use PROJECT=tcc2 by default; for the reproduction project,
use `sudo PROJECT=tcc2-repro ...` only when testing interventions.

## Manually remove the network delay (netem)
If the C6 scenario script is interrupted before cleanup, remove the rule from eth0 in the
NGINX container and use `tc qdisc show` to confirm that it has been removed:

```bash
sudo bash -c 'PID=$(docker inspect -f "{{.State.Pid}}" $(docker ps -q --filter label=com.docker.compose.project=tcc2 --filter label=com.docker.compose.service=nginx)); nsenter -t "$PID" -n tc qdisc del dev eth0 root; nsenter -t "$PID" -n tc qdisc show dev eth0'
```

## Stop the stack without losing data
`docker compose stop` (NEVER use `docker compose down -v`, which deletes the volumes).

---

[Return to the documentation index](../README.en.md)
