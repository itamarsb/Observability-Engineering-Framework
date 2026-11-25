# Instalação do Ubuntu Server

**Idioma:** [English (US)](ubuntu-server-installation.md) | **Português (Brasil)**

## Objetivo

Preparar o ambiente de laboratório para o Observability Engineering Framework.

## Configuração do laboratório com Ubuntu Server

## Ambiente

- Ubuntu Server 26.04 LTS
- Intel i7-2600
- 16 GB de RAM
- SSD de 480 GB
- Adaptador Wi-Fi USB Realtek RTL8188FTV

## Sistema operacional

Ubuntu Server LTS

## Serviços planejados

- NGINX
- FastAPI
- OpenTelemetry Collector
- Prometheus
- Grafana
- Loki
- Tempo

## Situação

- [X] Ubuntu instalado
- [X] IP estático configurado
- [X] SSH habilitado
- [X] Atualizações instaladas


# Evidências do laboratório

## Hardware do laboratório

![Hardware](../images/Ubuntu_Server_01.jpg)

## Seleção da distribuição

![Distribuição](../images/Ubuntu_Server_04.jpg)

## Particionamento

![Particionamento](../images/Ubuntu_Server_02.jpg)

## Instalação do Ubuntu Server

![Instalação](../images/Ubuntu_Server_06.jpg)

## Primeiro login

![Login](../images/Ubuntu_Server_09.jpg)

## Finalização

![Finalização](../images/Ubuntu_Server_14.jpg)

## Diagnóstico de problemas de rede

![Rede](../images/Ubuntu_Server_15.jpg)

## Verificação do acesso à internet

![Internet](../images/Ubuntu_Server_16.jpg)

## Validação

```bash
ping google.com
```

## Resultado:

- 0% de perda de pacotes
- Resolução de DNS bem-sucedida
- Conectividade com a internet confirmada

## Atualizações instaladas

![Validação](../images/Ubuntu_Server_17.jpg)

## Atualização completa do sistema:

```bash
sudo apt update
sudo apt upgrade -y
```

![Atualização](../images/Ubuntu_Server_19.jpg)

## Em seguida:

```bash
sudo reboot
```

![Reinicialização](../images/Ubuntu_Server_21.jpg)

## Após a reinicialização:

```bash
uname -a
```

## E:

```bash
hostnamectl
```

![Após a reinicialização](../images/Ubuntu_Server_20.jpg)

---

[Retornar ao índice da documentação](../README.md)
