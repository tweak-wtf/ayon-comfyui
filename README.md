# ayon-comfyui
An AYON Addon for launching ComfyUI locally via TrayLauncher.

Loads `ComfyUI` from offical GitHub repo and comes with `ComfyUI-Manager` preconfigured.

> ⚠️ **Warning:** This addon is Windows-only and depends on `uv` to be executable on your system.
> If `uv` is not found it will run the installation script from https://astral.sh/uv/install.ps1 for the current user.


It uses `git` from AYON's dependency package to clone `ComfyUI` and any custom plugins that are configured.
`uv` is used for installing all required dependencies and environment solving. This environment is used to run `ComfyUI` in a separate terminal session.

## Settings

### Repository Settings
![image](https://github.com/user-attachments/assets/a7ce0a8b-edac-4727-9df2-993d90150ba6)

### General Settings
![image](https://github.com/user-attachments/assets/ac2053a8-a751-4e07-bbcf-c53bcd5527d6)

### Caching Settings
![image](https://github.com/user-attachments/assets/28b558ee-a4f9-4e57-9961-570104b1f8d0)
