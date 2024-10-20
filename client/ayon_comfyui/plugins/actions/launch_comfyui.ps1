# assumes to be in comfyui directory
param(
    [switch]$useCpu = $false,
    [string[]]$plugins = @(),
    [string[]]$extraDependencies = @()
)

# ensure uv is installed
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path += ";$env:USERPROFILE\.cargo\bin"
}

# create local venv
uv venv --allow-existing
if (-not $?){
    Write-Output "Failed to create venv"
    exit 1
}
.venv\Scripts\activate

# Install requirements
Write-Output "Installing ComfyUI requirements"
uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124

# install plugins dependencies
foreach ($plugin in $plugins) {
    $plugin_requirements = ".\custom_nodes\$plugin\requirements.txt"
    if (Test-Path $plugin_requirements) {
        Write-Output "Installing $plugin dependencies"
        uv pip install -r $plugin_requirements
    }
}

# install extra plugin dependencies
Write-Output $extraDependencies.Count
if ($extraDependencies) {
    Write-Output "Installing extra dependencies"
    uv pip install $extraDependencies
}

# run the server
if ($useCpu) {
    Write-Output "Running ComfyUI with CPU"
    uv run .\main.py --cpu
} else {
    uv run .\main.py
}
