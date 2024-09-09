# assumes to be in comfyui directory
param(
    [switch]$useCpu = $false,
    [string[]]$plugins = @()
)

# Check for local venv
if (-not (Test-Path .\venv)) {
    uv venv
}
.venv\Scripts\activate

# Install requirements
Write-Output "Installing ComfyUI requirements"
uv pip install pip # needed by ComfyUI-Manager to install node deps
uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124

# install plugins dependencies
foreach ($plugin in $plugins) {
    $plugin_requirements = ".\custom_nodes\$plugin\requirements.txt"
    if (Test-Path $plugin_requirements) {
        Write-Output "Installing $plugin dependencies"
        uv pip install -r $plugin_requirements
    }
}


# run the server
if ($useCpu) {
    Write-Output "Running ComfyUI with CPU"
    uv run .\main.py --cpu
} else {
    uv run .\main.py
}
