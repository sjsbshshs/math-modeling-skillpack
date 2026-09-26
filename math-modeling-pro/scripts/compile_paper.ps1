[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PaperDirectory,

    [string]$MainTex = "论文.tex",

    [string]$TexBin,

    [ValidateRange(2, 5)]
    [int]$Passes = 2
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$paperPath = (Resolve-Path -LiteralPath $PaperDirectory).Path
$mainPath = Join-Path $paperPath $MainTex
if (-not (Test-Path -LiteralPath $mainPath -PathType Leaf)) {
    throw "Main TeX file not found: $mainPath"
}

function Find-XeLaTeX {
    param([string]$ExplicitTexBin)

    if ($ExplicitTexBin) {
        $candidate = Join-Path $ExplicitTexBin "xelatex.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        throw "xelatex.exe not found in TexBin: $ExplicitTexBin"
    }

    $command = Get-Command xelatex -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $roots = @("C:\texlive", "D:\texlive")
    $candidates = foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root -PathType Container) {
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                ForEach-Object {
                    $path = Join-Path $_.FullName "bin\windows\xelatex.exe"
                    if (Test-Path -LiteralPath $path -PathType Leaf) { $path }
                }
        }
    }
    $selected = $candidates | Select-Object -First 1
    if (-not $selected) {
        throw "XeLaTeX was not found in PATH or standard TeX Live directories. Pass -TexBin explicitly."
    }
    return $selected
}

$xelatex = Find-XeLaTeX -ExplicitTexBin $TexBin
Push-Location -LiteralPath $paperPath
try {
    for ($pass = 1; $pass -le $Passes; $pass++) {
        Write-Host "XeLaTeX pass $pass/$Passes"
        & $xelatex -interaction=nonstopmode -halt-on-error $MainTex
        if ($LASTEXITCODE -ne 0) {
            throw "XeLaTeX failed on pass $pass with exit code $LASTEXITCODE"
        }
    }

    $logPath = [IO.Path]::ChangeExtension($mainPath, ".log")
    $pdfPath = [IO.Path]::ChangeExtension($mainPath, ".pdf")
    if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
        throw "Compilation log not found: $logPath"
    }
    if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
        throw "Compiled PDF not found: $pdfPath"
    }

    $patterns = @(
        "Overfull \\[hv]box",
        "Underfull \\[hv]box",
        "Float too large",
        "LaTeX Font Warning",
        "There were undefined references",
        "Citation .+ undefined",
        "Reference .+ undefined",
        "Rerun to get cross-references right"
    )
    $warnings = Select-String -LiteralPath $logPath -Pattern $patterns
    if ($warnings) {
        $warnings | ForEach-Object { Write-Error $_.Line }
        throw "Compilation succeeded but target layout/reference warnings remain."
    }

    $file = Get-Item -LiteralPath $pdfPath
    Write-Host "PASS: $($file.FullName) ($($file.Length) bytes)"
}
finally {
    Pop-Location
}
