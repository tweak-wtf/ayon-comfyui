# assumes to be in comfyui directory
param(
    [switch]$useCpu = $false,
    [string]$cacheDir = "",
    [string[]]$plugins = @(),
    [string[]]$extraDependencies = @(),
    [string]$projectName = ""
)

# ensure uv is installed
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path += ";$env:USERPROFILE\.cargo\bin"
}

if ($cacheDir) {
    Write-Output "Setting cache directory to $cacheDir"
    $env:UV_CACHE_DIR = $cacheDir
}

# Determine the user localized venv path
$venvPath = ".venv"
if ($projectName) {
    $ayonComfyUIDir = Join-Path -Path $env:USERPROFILE -ChildPath "AYON\ComfyUI"
    if (-not (Test-Path $ayonComfyUIDir)) {
        New-Item -Path $ayonComfyUIDir -ItemType Directory -Force | Out-Null
    }
    $projectDir = Join-Path -Path $ayonComfyUIDir -ChildPath $projectName
    if (-not (Test-Path $projectDir)) {
        New-Item -Path $projectDir -ItemType Directory -Force | Out-Null
    }
    $venvPath = Join-Path -Path $projectDir -ChildPath ".venv"
    Write-Output "Using virtual environment at: $venvPath"
}

# create local venv
uv venv --allow-existing --python 3.12 $venvPath
if (-not $?){
    Write-Output "Failed to create venv"
    exit 1
}

# Add the activation script path
$activateScript = Join-Path -Path $venvPath -ChildPath "Scripts\Activate.ps1"

# Activate the venv using dot sourcing
Write-Output "Activating virtual environment from $activateScript"
. $activateScript

# Verify activation
if (-not $env:VIRTUAL_ENV) {
    Write-Output "Failed to activate virtual environment"
    exit 1
}

Write-Output "Virtual environment activated: $env:VIRTUAL_ENV"

# Install requirements
Write-Output "Installing ComfyUI requirements"
uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu126

# Make sure PyYAML is installed (seems to be missing)
uv pip install PyYAML

# install plugins dependencies
foreach ($plugin in $plugins) {
    $plugin_requirements = ".\custom_nodes\$plugin\requirements.txt"
    if (Test-Path $plugin_requirements) {
        Write-Output "Installing $plugin dependencies"
        uv pip install -r $plugin_requirements
    }
}

# install extra plugin dependencies
if ($extraDependencies) {
    Write-Output "Installing extra dependencies"
    uv pip install $extraDependencies
}

# run the server
if ($useCpu) {
    Write-Output "Running ComfyUI with CPU"
    python .\main.py --cpu
} else {
    python .\main.py
}
