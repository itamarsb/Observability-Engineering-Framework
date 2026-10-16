#!/usr/bin/env bash
# Inventario do SERVIDOR (somente leitura; nao altera nada).
# Uso: bash scripts/inventory_server.sh antes     (ou: depois, reimplantacao...)
# Saida: ~/tcc2-registros/ambiente-<rotulo>/*.txt  (copie depois para o notebook)
set -uo pipefail
LABEL="${1:-antes}"
D="$HOME/tcc2-registros/ambiente-${LABEL}"
mkdir -p "$D" && cd "$D" || exit 1
run() { local f="$1"; shift; { echo "\$ $*"; "$@"; } > "$f" 2>&1 || true; }
python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat())' > data-utc.txt
run sistema.txt        cat /etc/os-release
run kernel.txt         uname -a
run host.txt           hostnamectl
run cpu.txt            lscpu
run nproc.txt          nproc
run memoria.txt        free -h
run meminfo.txt        cat /proc/meminfo
run swap.txt           swapon --show
run discos.txt         lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL
run espaco.txt         df -hT
run interfaces.txt     ip -br link
run enderecos.txt      ip -br address
run rotas.txt          ip route
run usb.txt            lsusb
run relogio.txt        timedatectl status
run chrony.txt         chronyc tracking
run servicos-falhos.txt systemctl --failed --no-pager
run sensores.txt       sensors
run boot.txt           efibootmgr -v
run docker-versao.txt  docker version
run compose-versao.txt docker compose version
run docker-ps.txt      docker ps -a
run docker-volumes.txt docker volume ls
run stress-ng.txt      stress-ng --version
run python.txt         python3 --version
run sudo.txt           sudo --version
run pacotes.txt        dpkg-query -W
cat /sys/class/net/enp2s0/speed > enp2s0-velocidade.txt 2>&1 || true
# dmidecode exige root: modelo da placa, chassi e modulos de memoria
sudo dmidecode -t system -t baseboard -t chassis -t memory > hardware-dmi.txt 2>&1 || true
echo "Inventario salvo em $D"
ls -1 "$D"
