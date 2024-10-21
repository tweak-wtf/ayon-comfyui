# ayon-comfyui
An AYON Addon for launching ComfyUI locally via TrayLauncher.

Loads `ComfyUI` from offical GitHub repo and comes with `ComfyUI-Manager` preconfigured.

> ⚠️ **Warning:** This addon is Windows-only and depends on `uv` to be executable on your system.
> If `uv` is not found it will run the installation script from https://astral.sh/uv/install.ps1 for the current user.


It uses `git` from AYON's dependency package to clone `ComfyUI` and any custom plugins that are configured.
`uv` is used for installing all required dependencies and environment solving. This environment is used to run `ComfyUI` in a separate terminal session.

## Settings

### Repository Settings
![image](image.png)

### General Settings
![image](image-1.png)

### Caching Settings
![image](image-2.png)
