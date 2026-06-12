# Ubuntu Server Installation

## Objective

Prepare the laboratory environment for the Observability Engineering Framework.

## Ubuntu Server Lab Setup

## Environment

- Ubuntu Server 26.04 LTS
- Intel i7-2600
- 16 GB RAM
- SSD 480 GB
- Wi-Fi USB Realtek RTL8188FTV

## Operating System

Ubuntu Server LTS

## Planned Services

- NGINX
- FastAPI
- OpenTelemetry Collector
- Prometheus
- Grafana
- Loki
- Tempo

## Status

- [X] Ubuntu Installed
- [X] Static IP Configured
- [X] SSH Enabled
- [X] Updates Installed


# Laboratory Evidence

## Hardware Lab

![Hardware](../images/Ubuntu_Server_01.jpg)

## Distribution selection

![Distribution](../images/Ubuntu_Server_04.jpg)

## Partitioning

![Partitioning](../images/Ubuntu_Server_02.jpg)

## Ubuntu Server Installation

![Installation](../images/Ubuntu_Server_06.jpg)

## First Login

![Login](../images/Ubuntu_Server_09.jpg)

## Finalization

![Finalization](../images/Ubuntu_Server_14.jpg)

## Network Troubleshooting

![Network](../images/Ubuntu_Server_15.jpg)

## Internet Access Verification

![Internet](../images/Ubuntu_Server_16.jpg)

## Validation

```bash
ping google.com
```

## Result:

- 0% packet loss
- Successful DNS resolution
- Internet connectivity confirmed

## Updates Installed

![Valid](../images/Ubuntu_Server_17.jpg)

## Completely update the system:

```bash
sudo apt update
sudo apt upgrade -y
```

![Update](../images/Ubuntu_Server_19.jpg)

## Then:

```bash
sudo reboot
```

![Reboot](../images/Ubuntu_Server_21.jpg)

## After restarting:

```bash
uname -a
```

## And:

```bash
hostnamectl
```

