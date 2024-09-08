# ayon-comfyui
An AYON Addon for launching ComfyUI locally.

> ⚠️ **Warning:** This addon is Windows-only and depends on `conda` to be executable on your system.


## Settings
Loads `ComfyUI` from offical GitHub repo and comes with `ComfyUI-Manager` preconfigured.

Use `checkpoints_dir` to copy checkpoints to configured repository root. 

![image](https://github.com/user-attachments/assets/b5a87879-e207-426d-bf13-34807f74ab87)

## How it works
This addon uses `git` from AYON's dependency package to clone `ComfyUI` and any custom plugins that are configured.
`conda` is used to build a local python environment `ayon_comfyui` for installing all required dependencies. This environment is used to run `ComfyUI` in a separate terminal session.
