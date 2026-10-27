# Detiene los servidores de IETABA iniciados con iniciar_en_segundo_plano.ps1
# (los que escuchan en los puertos 8000 y 8443).

foreach ($puerto in 8000, 8443) {
    $conexiones = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conexiones) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Servidor del puerto $puerto detenido."
    }
}
