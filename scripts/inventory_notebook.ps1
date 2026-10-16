# Inventario do NOTEBOOK (PowerShell no Windows 11; somente leitura).
# Uso: powershell -ExecutionPolicy Bypass -File .\inventory_notebook.ps1
# Saida: notebook-inventario.txt na pasta atual (guarde em TCC2\evidencias\00-ambiente\notebook)
$out = "notebook-inventario.txt"
"Data UTC: $((Get-Date).ToUniversalTime().ToString('o'))" | Out-File $out -Encoding utf8
Get-ComputerInfo -Property OsName,OsVersion,OsBuildNumber,CsManufacturer,CsModel,CsProcessors,CsTotalPhysicalMemory |
  Format-List | Out-File $out -Append -Encoding utf8
"`n== WSL ==" | Out-File $out -Append -Encoding utf8
wsl --version 2>&1 | Out-File $out -Append -Encoding utf8
wsl -l -v 2>&1 | Out-File $out -Append -Encoding utf8
"`n== .wslconfig (modo de rede do WSL2; sem arquivo = NAT) ==" | Out-File $out -Append -Encoding utf8
if (Test-Path "$env:USERPROFILE\.wslconfig") { Get-Content "$env:USERPROFILE\.wslconfig" | Out-File $out -Append -Encoding utf8 } else { "(nao existe: NAT)" | Out-File $out -Append -Encoding utf8 }
"`n== Adaptadores de rede ==" | Out-File $out -Append -Encoding utf8
Get-NetAdapter | Format-Table Name,InterfaceDescription,Status,LinkSpeed -AutoSize | Out-File $out -Append -Encoding utf8
Get-NetIPAddress -AddressFamily IPv4 | Format-Table InterfaceAlias,IPAddress,PrefixLength -AutoSize | Out-File $out -Append -Encoding utf8
"`n== Plano de energia ==" | Out-File $out -Append -Encoding utf8
powercfg /getactivescheme | Out-File $out -Append -Encoding utf8
"`n== Sincronizacao de horario ==" | Out-File $out -Append -Encoding utf8
w32tm /query /status 2>&1 | Out-File $out -Append -Encoding utf8
"`n== OpenSSH cliente ==" | Out-File $out -Append -Encoding utf8
ssh -V 2>&1 | Out-File $out -Append -Encoding utf8
Write-Host "Inventario salvo em $out"
