# assumes to be in comfyui directory
param(
    [string]$cacheDir = "",
    [string]$pypiUrl = "",
    [string]$pythonVersion = "",
    [string[]]$plugins = @(),
    [string[]]$extraFlags = @(),
    [string[]]$extraDependencies = @()
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

# create local venv
uv venv --allow-existing --python $pythonVersion
if (-not $?){
    Write-Output "Failed to create venv"
    exit 1
}
.venv\Scripts\activate

# Install requirements
Write-Output "Installing PyTorch with CUDA support"
uv pip install --pre torch torchvision torchaudio --index-url $pypiUrl
Write-Output "Installing ComfyUI requirements"
uv pip install -r requirements.txt

# Manifest file path
$manifestPath = ".\dependencies_manifest.json"

# Function to read manifest file
function Read-Manifest {
    if (Test-Path $manifestPath) {
        try {
            $content = Get-Content $manifestPath -Raw
            return $content | ConvertFrom-Json
        }
        catch {
            Write-Output "Error reading manifest file, creating new one"
            return @{
                core_dependencies = @()
                plugin_dependencies = @{}
                extra_dependencies = @()
                last_updated = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            }
        }
    }
    return @{
        core_dependencies = @()
        plugin_dependencies = @{}
        extra_dependencies = @()
        last_updated = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
}

# Function to write manifest file
function Write-Manifest {
    param($manifest)
    $manifest.last_updated = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $manifest | ConvertTo-Json -Depth 10 | Set-Content $manifestPath
    Write-Output "Manifest updated: $manifestPath"
}

# Function to get dependencies from a requirements.txt file
function Get-PluginDependencies {
    param([string]$requirementsPath)
    if (Test-Path $requirementsPath) {
        $dependencies = @()
        Get-Content $requirementsPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                # Extract package name (remove version specifiers)
                $packageName = $line -split '[<>=!~]' | Select-Object -First 1
                $dependencies += $packageName.Trim()
            }
        }
        return $dependencies
    }
    return @()
}

# Function to remove package from UV environment
function Remove-PackageFromUV {
    param([string]$packageName)
    Write-Output "Removing package: $packageName"
    uv pip uninstall $packageName
}

# Function to get currently installed packages
function Get-InstalledPackages {
    $installed = uv pip list --format json | ConvertFrom-Json
    return $installed | ForEach-Object { $_.name }
}

# Load existing manifest
$manifest = Read-Manifest

# Plugin cleanup and dependency management
Write-Output "Starting plugin cleanup and dependency management..."

# Get existing plugins in custom_nodes directory
$customNodesPath = ".\custom_nodes"
$existingPlugins = @()
if (Test-Path $customNodesPath) {
    $existingPlugins = Get-ChildItem -Path $customNodesPath -Directory | ForEach-Object { $_.Name }
}

# Find plugins to remove (existing but not in plugins list)
$pluginsToRemove = $existingPlugins | Where-Object { $_ -notin $plugins }

# Create a map of all plugin dependencies for tracking
$allPluginDependencies = @{}
$pluginsToKeep = $existingPlugins | Where-Object { $_ -in $plugins }

# Build dependency map for plugins we're keeping
foreach ($plugin in $pluginsToKeep) {
    $requirementsPath = ".\custom_nodes\$plugin\requirements.txt"
    $dependencies = Get-PluginDependencies -requirementsPath $requirementsPath
    $allPluginDependencies[$plugin] = $dependencies
}

# Build dependency map for plugins we're removing
$removedPluginDependencies = @{}
foreach ($plugin in $pluginsToRemove) {
    $requirementsPath = ".\custom_nodes\$plugin\requirements.txt"
    $dependencies = Get-PluginDependencies -requirementsPath $requirementsPath
    $removedPluginDependencies[$plugin] = $dependencies
}

# Remove unwanted plugins
foreach ($plugin in $pluginsToRemove) {
    $pluginPath = ".\custom_nodes\$plugin"
    Write-Output "Removing plugin: $plugin"
    if (Test-Path $pluginPath) {
        Remove-Item -Path $pluginPath -Recurse -Force
    }
    # Remove from manifest
    if ($manifest.plugin_dependencies.PSObject.Properties.Name -contains $plugin) {
        $manifest.plugin_dependencies.PSObject.Properties.Remove($plugin)
    }
}

# Find dependencies that are no longer needed
$allRemovedDependencies = @()
foreach ($dependencies in $removedPluginDependencies.Values) {
    $allRemovedDependencies += $dependencies
}

$allKeptDependencies = @()
foreach ($dependencies in $allPluginDependencies.Values) {
    $allKeptDependencies += $dependencies
}

# Get ComfyUI base requirements to protect them from deletion
$comfyuiBaseRequirements = Get-PluginDependencies -requirementsPath "requirements.txt"
Write-Output "ComfyUI base requirements (protected): $($comfyuiBaseRequirements -join ', ')"

# Find dependencies that were only used by removed plugins
# Exclude ComfyUI base requirements from deletion
$dependenciesToRemove = $allRemovedDependencies | Where-Object { 
    $_ -notin $allKeptDependencies -and $_ -notin $comfyuiBaseRequirements 
} | Sort-Object -Unique

Write-Output "Found $($dependenciesToRemove.Count) dependencies to remove: $($dependenciesToRemove -join ', ')"

# Remove unused dependencies
foreach ($dependency in $dependenciesToRemove) {
    try {
        Remove-PackageFromUV -packageName $dependency
    }
    catch {
        Write-Output "Warning: Failed to remove package $dependency - $_"
    }
}

# install plugins dependencies
foreach ($plugin in $plugins) {
    $plugin_requirements = ".\custom_nodes\$plugin\requirements.txt"
    if (Test-Path $plugin_requirements) {
        Write-Output "Installing $plugin dependencies"
        uv pip install -r $plugin_requirements
        
        # Update manifest with plugin dependencies
        $dependencies = Get-PluginDependencies -requirementsPath $plugin_requirements
        $manifest.plugin_dependencies[$plugin] = $dependencies
    }
}

# install extra plugin dependencies
if ($extraDependencies) {
    Write-Output "Installing extra dependencies"
    uv pip install $extraDependencies
    $manifest.extra_dependencies = $extraDependencies
}

# Update core dependencies in manifest
$manifest.core_dependencies = @("torch", "torchvision", "torchaudio")
$comfyuiRequirements = Get-PluginDependencies -requirementsPath "requirements.txt"
$manifest.core_dependencies += $comfyuiRequirements
Write-Output "Core dependencies tracked in manifest: $($manifest.core_dependencies -join ', ')"

# Get currently installed packages and update manifest
$installedPackages = Get-InstalledPackages
$manifest.installed_packages = $installedPackages

# Write updated manifest
Write-Manifest -manifest $manifest

$uv_command = @(".\main.py")
if ($extraFlags) {
    foreach ($flag in $extraFlags) {
        $uv_command += $flag
    }
}

$env:OPENCV_IO_ENABLE_OPENEXR = "1" # workaround for opencv error

# run the server
Write-Output $uv_command
uv run $uv_command
