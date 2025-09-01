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

# Function to get dependencies from a requirements.txt file
function Get-PluginDependencies {
    param([string]$requirementsPath)
    if (Test-Path $requirementsPath) {
        $dependencies = @()
        Get-Content $requirementsPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                # Extract package name (remove version specifiers and handle all pip requirement syntax)
                # Handle operators: ==, >=, <=, >, <, !=, ~=, ===
                # Handle extras: package[extra1,extra2]
                # Handle URLs and VCS: git+https://...
                $packageName = ""
                if ($line -match '^([a-zA-Z0-9_-]+)') {
                    $packageName = $matches[1]
                } elseif ($line -match '^git\+.*#egg=([a-zA-Z0-9_-]+)') {
                    $packageName = $matches[1]
                } else {
                    # Fallback: split on common operators and take first part
                    $packageName = ($line -split '[<>=!~\[\s]')[0]
                }
                if ($packageName) {
                    $dependencies += $packageName.Trim()
                }
            }
        }
        return $dependencies
    }
    return @()
}

# Function to collect dependencies from multiple plugins
function Get-Dependencies {
    param($fromPlugins)
    $result = @{}
    foreach ($plugin in $fromPlugins) {
        $requirementsPath = ".\custom_nodes\$plugin\requirements.txt"
        $dependencies = Get-PluginDependencies -requirementsPath $requirementsPath
        $result[$plugin] = $dependencies
    }
    return $result
}

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

# install temp venv to get protected dependencies
$tempVenv = ".venv-baseline"
& $uv venv $tempVenv --python $pythonVersion
& "$tempVenv\Scripts\activate"
& $uv pip install --pre torch torchvision torchaudio --index-url $pypiUrl
& $uv pip install -r requirements.txt
$baselineDependencies = & $uv pip list --format json | ConvertFrom-Json
$protectedDependencies = $baselineDependencies | ForEach-Object { $_.name }
deactivate
Remove-Item -Path $tempVenv -Recurse -Force

# create local venv
& $uv venv --allow-existing --python $pythonVersion
if (-not $?) {
    Write-Output "Failed to create venv"
    exit 1
}
.venv\Scripts\activate
& $uv pip install --pre torch torchvision torchaudio --index-url $pypiUrl
& $uv pip install -r requirements.txt

# Get existing plugins in custom_nodes directory
$customNodesPath = ".\custom_nodes"
$existingPlugins = @()
if (Test-Path $customNodesPath) {
    $existingPlugins = Get-ChildItem -Path $customNodesPath -Directory | ForEach-Object { $_.Name }
}

# Find plugins to remove (existing but not in plugins list)
$pluginsToRemove = $existingPlugins | Where-Object { $_ -notin $plugins }
$pluginsToKeep = $existingPlugins | Where-Object { $_ -in $plugins }

# Build dependency maps using the refactored function
$allPluginDependencies = Get-Dependencies $pluginsToKeep
$removedPluginDependencies = Get-Dependencies $pluginsToRemove

# Remove unwanted plugins
foreach ($plugin in $pluginsToRemove) {
    $pluginPath = ".\custom_nodes\$plugin"
    Write-Output "Removing plugin: $plugin"
    if (Test-Path $pluginPath) {
        Remove-Item -Path $pluginPath -Recurse -Force
    }
}

# Find dependencies that were used by removed plugins
# Use the captured protected dependencies (includes all transitive deps) instead of just requirements.txt
$dependenciesToRemove = ($removedPluginDependencies.Values | ForEach-Object { $_ }) | Where-Object { 
    $_ -notin ($allPluginDependencies.Values | ForEach-Object { $_ }) -and $_ -notin $protectedDependencies 
} | Sort-Object -Unique
if ($dependenciesToRemove.Count -gt 0) {
    Write-Output "Found $($dependenciesToRemove.Count) dependencies to remove: $($dependenciesToRemove -join ', ')"
    foreach ($dependency in $dependenciesToRemove) {
        uv pip uninstall $dependency
    }
}

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
