$ErrorActionPreference = "Stop"

$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$rutaEjemplo = Join-Path $raiz ".env.example"
$rutaEntorno = Join-Path $raiz ".env"
$valoresActuales = @{}

if (Test-Path $rutaEntorno) {
    foreach ($linea in Get-Content $rutaEntorno) {
        if ($linea -match "^([^#=]+)=(.*)$") {
            $valoresActuales[$matches[1]] = $matches[2]
        }
    }
}

$clavesSecretas = @(
    "DJANGO_SECRET_KEY",
    "POSTGRES_ADMIN_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "POSTGRES_MIGRATION_PASSWORD",
    "POSTGRES_REPORT_PASSWORD",
    "POSTGRES_BACKUP_PASSWORD",
    "MONGO_ROOT_PASSWORD",
    "MONGO_APP_PASSWORD",
    "MONGO_REPORT_PASSWORD",
    "MONGO_BACKUP_PASSWORD"
)
$salida = foreach ($linea in Get-Content $rutaEjemplo) {
    if ($linea -match "^([^#=]+)=(.*)$") {
        $clave = $matches[1]
        $valorEjemplo = $matches[2]
        if ($clave -in $clavesSecretas) {
            $valorActual = $valoresActuales[$clave]
            if ([string]::IsNullOrWhiteSpace($valorActual) -or
                $valorActual -match "^(generate-|replace-)") {
                $bytes = New-Object byte[] 32
                $generador = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
                $generador.GetBytes($bytes)
                $generador.Dispose()
                $valorActual = [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
            }
            "$clave=$valorActual"
        }
        elseif ($valoresActuales.ContainsKey($clave)) {
            "$clave=$($valoresActuales[$clave])"
        }
        else {
            "$clave=$valorEjemplo"
        }
    }
    else {
        $linea
    }
}

$utf8SinBOM = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($rutaEntorno, [string[]]$salida, $utf8SinBOM)
Write-Output "Archivo .env local preparado con credenciales aleatorias. No compartas ni publiques ese archivo."
