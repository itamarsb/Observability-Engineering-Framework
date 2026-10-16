#!/usr/bin/env bash
# Instala os scripts de intervencao em /usr/local/sbin (dono root, 755) e a regra sudoers
# restrita a eles. Rodar no SERVIDOR, na raiz do repositorio:  sudo bash scripts/install_server_scripts.sh itamar
set -euo pipefail
USER_NAME="${1:?informe o usuario, ex.: itamar}"
for s in tcc2-cpu tcc2-mem tcc2-net tcc2-apifail; do
  install -o root -g root -m 0755 "experiments/stress-ng/${s}.sh" "/usr/local/sbin/${s}.sh"
done
TMP=$(mktemp)
echo "${USER_NAME} ALL=(root) NOPASSWD: /usr/local/sbin/tcc2-cpu.sh, /usr/local/sbin/tcc2-mem.sh, /usr/local/sbin/tcc2-net.sh, /usr/local/sbin/tcc2-apifail.sh" > "$TMP"
visudo -cf "$TMP"                      # valida a sintaxe antes de instalar
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/tcc2
rm -f "$TMP"
echo "Instalado. Teste sem senha:  sudo -n /usr/local/sbin/tcc2-cpu.sh 10 50"
