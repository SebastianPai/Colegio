# Levanta el servidor por HTTPS (puerto 8443) para que el escaner de
# documentos pueda usar la camara desde el celular dentro de la red del
# colegio (getUserMedia exige un contexto seguro: HTTPS o localhost).
#
# Requiere haber generado el certificado antes, una sola vez (o de nuevo
# si cambia la IP de este equipo):
#   .\venv\Scripts\python.exe generar_certificado_https.py
#
# El servidor normal por HTTP (puerto 8000, sin este script) sigue
# funcionando igual que siempre — este es un servidor adicional, no un
# reemplazo.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\certs\server-cert.pem")) {
    Write-Host "No hay certificado generado todavia." -ForegroundColor Yellow
    Write-Host "Ejecuta primero: .\venv\Scripts\python.exe generar_certificado_https.py" -ForegroundColor Yellow
    exit 1
}

# El firewall de Windows bloquea por defecto las conexiones entrantes de
# otros equipos (el celular) a un puerto nuevo, aunque el servidor si
# responda en localhost. Sin esta regla, desde el celular la pagina
# simplemente no carga (no es un error del certificado).
$reglaExiste = Get-NetFirewallRule -DisplayName "IETABA App HTTPS" -ErrorAction SilentlyContinue
if (-not $reglaExiste) {
    Write-Host "Falta el permiso de firewall para el puerto 8443 — sin esto, el celular no puede conectarse aunque el servidor si este corriendo." -ForegroundColor Yellow
    try {
        New-NetFirewallRule -DisplayName "IETABA App HTTPS" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Any -ErrorAction Stop | Out-Null
        Write-Host "Regla de firewall creada." -ForegroundColor Green
    } catch {
        Write-Host "No se pudo crear la regla automaticamente (hace falta ser Administrador)." -ForegroundColor Red
        Write-Host "Abre PowerShell como Administrador y ejecuta una vez:" -ForegroundColor Yellow
        Write-Host '  New-NetFirewallRule -DisplayName "IETABA App HTTPS" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Any' -ForegroundColor Yellow
        Write-Host "El servidor va a arrancar igual, pero el celular no va a poder entrar hasta que agregues esa regla." -ForegroundColor Yellow
    }
}

Write-Host "Iniciando servidor HTTPS en el puerto 8443..." -ForegroundColor Cyan
& .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs/server-key.pem --ssl-certfile certs/server-cert.pem
