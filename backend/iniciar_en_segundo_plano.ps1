# Arranca el sistema IETABA en segundo plano (sin ventanas abiertas):
#   - http://<IP-o-nombre-del-PC>:8000   (computadores de la red)
#   - https://<IP-o-nombre-del-PC>:8443  (celulares: app instalable y uso sin wifi)
# Siguen corriendo aunque se cierre esta ventana; se detienen al apagar el
# PC o con .\detener_servidor.ps1. Los mensajes quedan en backend\logs\.
#
# No toca el firewall (eso lo hace iniciar_https.ps1, como Administrador).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force "logs" | Out-Null

function Iniciar($puerto, $argumentosExtra) {
    $ocupado = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
    if ($ocupado) {
        Write-Host "Puerto $puerto ya está en uso: el servidor ya estaba corriendo." -ForegroundColor Yellow
        return
    }
    $argumentos = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$puerto") + $argumentosExtra
    Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList $argumentos -WindowStyle Hidden `
        -RedirectStandardOutput "logs\servidor_$puerto.log" -RedirectStandardError "logs\servidor_${puerto}_errores.log"
    Write-Host "Servidor iniciado en el puerto $puerto." -ForegroundColor Green
}

Iniciar 8000 @()
if (Test-Path ".\certs\server-cert.pem") {
    # Si el router le cambió la IP a este PC, el certificado se renueva solo
    # (sumando la IP nueva); si no, no hace nada.
    & ".\venv\Scripts\python.exe" generar_certificado_https.py --si-cambio-ip | Select-Object -First 1 | Write-Host
    Iniciar 8443 @("--ssl-keyfile", "certs/server-key.pem", "--ssl-certfile", "certs/server-cert.pem")
} else {
    Write-Host "Sin certificado HTTPS: genera uno con .\venv\Scripts\python.exe generar_certificado_https.py" -ForegroundColor Yellow
}

$nombre = $env:COMPUTERNAME.ToLower()
# Android (Chrome) no reconoce los nombres .local: en los celulares hay que
# entrar por la IP de este PC en el wifi del colegio.
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.PrefixOrigin -in @("Dhcp", "Manual") -and $_.InterfaceAlias -notmatch "vEthernet|WSL|Loopback" -and $_.IPAddress -notlike "169.254*" } |
    Select-Object -ExpandProperty IPAddress
Write-Host ""
Write-Host "Computadores:  http://${nombre}.local:8000" -ForegroundColor Cyan
Write-Host "Celulares:     https://${nombre}.local:8443   (iPhone)" -ForegroundColor Cyan
foreach ($ip in $ips) {
    Write-Host "Android:       https://${ip}:8443   (o http://${ip}:8000)" -ForegroundColor Cyan
}
