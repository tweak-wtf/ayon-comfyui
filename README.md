# ayon-comfyui
An AYON Addon for launching ComfyUI locally via TrayLauncher.

Loads `ComfyUI` from offical GitHub repo and comes with `ComfyUI-Manager` preconfigured.

> ⚠️ **Warning:** This addon is Windows-only and depends on `uv` to be executable on your system.
> If `uv` is not found it will run the installation script from https://astral.sh/uv/install.ps1 for the current user.


It's Launcher Action uses `git` from AYON's dependency package to clone `ComfyUI` and any custom plugins that are configured.
`uv` is used for installing all required dependencies and environment solving in a separate terminal session. This session is used to launch a local `ComfyUI` server.

## Settings
> ✏️ All directory inputs support anatomy template strings and absolute paths.

### Repository Settings
Configure where to pull ComfyUI sources, its target directory and additional plugins.
You can specify extra dependencies to be installed as some custom nodes don't maintain a `requirements.txt`. All configured plugin dependencies will be collected and installed in a single `uv pip install`.

![image](https://github.com/user-attachments/assets/a7ce0a8b-edac-4727-9df2-993d90150ba6)

### General Settings
Toggle CPU-only mode and configure custom models. Toggle extra models to consider them during launch. You can add multiple directories per model type. They will be added to the ComfyUI repo directory's `extra_model_paths.yaml`. When using `copy_to_base` the directories won't be added to the config yaml but copied into the repo base's `models/{model_type}`.

> ⚠️ `copy_to_base` currently just blindly copies every file found in the directory. No filtering for files yet.

![image](https://github.com/user-attachments/assets/ac2053a8-a751-4e07-bbcf-c53bcd5527d6)

### Caching Settings
Configure whether `uv` should use a specific cache location to read and write to. Currently only configures `UV_CACHE_DIR` during the launch script but it seems to do the job.
Could be used in air-gapped scenarios.


![image](https://github.com/user-attachments/assets/28b558ee-a4f9-4e57-9961-570104b1f8d0)

### Plugin and Dependency Management
The addon automatically manages plugins and their dependencies to maintain a clean ComfyUI environment. When launching ComfyUI, the system performs the following cleanup operations:

#### Plugin Cleanup
- **Removes unwanted plugins**: Any plugins found in the `custom_nodes` directory that are not in the configured plugins list are automatically deleted
- **Preserves configured plugins**: Only plugins specified in the Repository Settings are kept

#### Dependency Management
- **Tracks all dependencies**: Maintains a comprehensive manifest of all installed packages and their sources
- **Removes unused dependencies**: Automatically uninstalls packages that were only used by removed plugins
- **Protects core dependencies**: ComfyUI base requirements from `requirements.txt` are never deleted, ensuring core functionality remains intact
- **Manifest tracking**: Creates and maintains a `dependencies_manifest.json` file that tracks:
  - Core ComfyUI dependencies
  - Plugin-specific dependencies
  - Extra dependencies
  - Currently installed packages
  - Last update timestamp

#### Manifest File
The `dependencies_manifest.json` file is created in the ComfyUI directory and provides a complete audit trail of the environment state. This enables:
- **Reproducible environments**: Exact dependency state can be recreated
- **Debugging**: Easy identification of which plugins require which dependencies
- **Cleanup validation**: Verification of what should be removed vs. what's actually installed

> ⚠️ **Note:** The cleanup process is automatic and cannot be disabled. Ensure your plugin configuration is correct before launching to avoid unintended plugin removal.
