param(
    [switch]$useCpu = $false
)

# Define the name of the conda environment
$envName = "ayon_comfyui"


# Check if the conda environment exists
$envExists = conda env list | Select-String -Pattern "^\s*$envName\s"

if (-not $envExists) {
    # Create the conda environment if it does not exist
    Write-Output "Creating conda environment: $envName"
    conda create -n $envName python -y
} else {
    Write-Output "Conda environment '$envName' already exists."
}

# Activate the conda environment
conda activate $envName
conda info

# Install requirements from requirements.txt
# use python -I -m pip instead of pip to avoid environment conflicts
python -I -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124

# run the server
if ($useCpu) {
    python .\main.py --cpu
} else {
    python .\main.py
}
