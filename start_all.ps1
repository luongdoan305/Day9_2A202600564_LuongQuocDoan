param(
    [string]$PythonRunner = "uv run python"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting Legal Multi-Agent System services..."
Write-Host "Registry starts first, then leaf agents, then orchestrators."
Write-Host ""

$services = @(
    @{ Name = "Registry"; Command = "$PythonRunner -m registry"; Port = 10000; Delay = 2 },
    @{ Name = "Tax Agent"; Command = "$PythonRunner -m tax_agent"; Port = 10102; Delay = 1 },
    @{ Name = "Compliance Agent"; Command = "$PythonRunner -m compliance_agent"; Port = 10103; Delay = 3 },
    @{ Name = "Law Agent"; Command = "$PythonRunner -m law_agent"; Port = 10101; Delay = 3 },
    @{ Name = "Customer Agent"; Command = "$PythonRunner -m customer_agent"; Port = 10100; Delay = 1 }
)

$processes = @()

try {
    foreach ($svc in $services) {
        Write-Host "Starting $($svc.Name) on port $($svc.Port)..."
        $process = Start-Process powershell `
            -ArgumentList "-NoExit", "-Command", "Set-Location '$PWD'; $($svc.Command)" `
            -PassThru
        $processes += $process
        Start-Sleep -Seconds $svc.Delay
    }

    Write-Host ""
    Write-Host "All services started:"
    Write-Host "  Registry:         http://localhost:10000"
    Write-Host "  Customer Agent:   http://localhost:10100"
    Write-Host "  Law Agent:        http://localhost:10101"
    Write-Host "  Tax Agent:        http://localhost:10102"
    Write-Host "  Compliance Agent: http://localhost:10103"
    Write-Host ""
    Write-Host "Run the end-to-end client:"
    Write-Host "  uv run python test_client.py"
    Write-Host ""
    Write-Host "Watch the service windows for the trace_id printed by test_client.py."
    Write-Host "Press Enter here to stop all services."
    Read-Host | Out-Null
}
finally {
    Write-Host "Stopping services..."
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}
