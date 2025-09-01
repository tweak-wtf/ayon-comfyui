# assumes to be in comfyui directory
param(
    [string]$uvPath = "",
    [string]$cacheDir = "",
    [string]$pypiUrl = "",
    [string]$pythonVersion = "",
    [string[]]$plugins = @(),
    [string[]]$extraFlags = @(),
    [string[]]$extraDependencies = @()
)

# ensure uv is installed
$uv = "uv"
if ($uvPath) {
    Write-Output "Using uv from: $uvPath"
    $uv = $uvPath
}
if ((-not $uvPath) -and (-not (Get-Command $uv -ErrorAction SilentlyContinue))) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path += ";$env:USERPROFILE\.cargo\bin"
}

if ($cacheDir) {
    Write-Output "Setting cache directory to $cacheDir"
    $env:UV_CACHE_DIR = $cacheDir
}

# create local venv
& $uv venv --allow-existing --python $pythonVersion
if (-not $?) {
    Write-Output "Failed to create venv"
    exit 1
}
.venv\Scripts\activate

# Install requirements
Write-Output "Installing PyTorch with CUDA support"
& $uv pip install --pre torch torchvision torchaudio --index-url $pypiUrl
Write-Output "Installing ComfyUI requirements"
& $uv pip install -r requirements.txt

# install plugins dependencies
foreach ($plugin in $plugins) {
    $plugin_requirements = ".\custom_nodes\$plugin\requirements.txt"
    if (Test-Path $plugin_requirements) {
        Write-Output "Installing $plugin dependencies"
        & $uv pip install -r $plugin_requirements
    }
}

# install extra plugin dependencies
if ($extraDependencies) {
    Write-Output "Installing extra dependencies"
    & $uv pip install $extraDependencies
}

$uv_command = @(".\main.py")
if ($extraFlags) {
    foreach ($flag in $extraFlags) {
        $uv_command += $flag
    }
}

$env:OPENCV_IO_ENABLE_OPENEXR = "1" # workaround for opencv error

# run the server
Write-Output $uv_command
& $uv run $uv_command
