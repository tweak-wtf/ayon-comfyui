from pathlib import Path

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
)


class RepositorySettings(BaseSettingsModel):
    url: str = SettingsField(default="", description="Repository URL.", title="URL")
    tag: str = SettingsField(
        default="", description="Repository tag. Leave empty for latest."
    )
    name: str = SettingsField(default="", description="Repository name.", title="Name")

    def __init__(self, **data):
        super().__init__(**data)
        self.name = Path(self.url).stem


class VirtualEnvSettings(BaseSettingsModel):
    uv_path: str = SettingsField(
        default="",
        title="UV Executable Path",
        description="Must be the explicit path to the UV executable.",
    )
    python_version: str = SettingsField(
        default="3.12",
        title="Python Version",
        description="Python version to use for the virtual environment.",
    )
    use_torch_nightly: bool = SettingsField(
        default=True,
        title="Use PyTorch Nightly",
        description="Use the nightly version of PyTorch.",
    )


class CustomNodeSettings(RepositorySettings):
    extra_dependencies: list[str] = SettingsField(
        default_factory=list,
        description="Extra python dependencies to install.",
        title="Extra Dependencies",
    )


class ComfyUIExtraModelSettings(BaseSettingsModel):
    enabled: bool = SettingsField(default=False)
    dir_template: str = SettingsField(
        default_factory=list,
        title="Source Directory",
        description="Where to load extra models from. Can also contain template keys",
    )
    copy_to_base: bool = SettingsField(
        default=False,
        title="Copy to Base",
        description="Copy all found extra models to their respective ComfyUI base directory.",
    )


class ComfyUIRepositorySettings(BaseSettingsModel):
    base_template: str = SettingsField(
        default="",
        title="Repository Root Template",
        description="Where to clone the ComfyUI repository to.",
    )
    base_url: str = SettingsField(
        default="",
        title="Repository URL",
        description="Where to clone the ComfyUI repository from.",
    )
    plugins: list[CustomNodeSettings] = SettingsField(
        default_factory=list[CustomNodeSettings],
        description="Repository Settings for Extra Nodes.",
    )


class ComfyUICachingSettings(BaseSettingsModel):
    enabled: bool = SettingsField(
        default=False,
    )
    cache_dir_template: str = SettingsField(
        default="",
        title="Cache Directory Template",
        description="Where to load dependencies from.",
    )


class AddonSettings(BaseSettingsModel):
    """ComfyUI addon settings."""

    extra_flags: list[str] = SettingsField(
        default=[],
        title="Extra Flags",
        description="Extra argument flags to pass when launching the ComfyUI server.",
    )
    venv: VirtualEnvSettings = SettingsField(
        default_factory=VirtualEnvSettings,
        title="Virtual Environment Settings",
        description="Virtual Environment Settings for the ComfyUI server.",
    )
    repositories: ComfyUIRepositorySettings = SettingsField(
        default_factory=ComfyUIRepositorySettings,
        title="Repository Settings",
        description="Git Repository Settings.",
    )
    extra_models: ComfyUIExtraModelSettings = SettingsField(
        default_factory=ComfyUIExtraModelSettings,
    )
    caching: ComfyUICachingSettings = SettingsField(
        default_factory=ComfyUICachingSettings,
        title="Caching Settings",
        description="Can be used in air gapped scenarios.",
    )


DEFAULT_VALUES = {
    "repositories": {
        "base_template": "{root[work]}/{project[name]}/comfyui",
        "base_url": "https://github.com/comfyanonymous/ComfyUI.git",
        "plugins": [
            {
                "url": "https://github.com/ltdrdata/ComfyUI-Manager.git",
                "extra_dependencies": ["pip"],
            }
        ],
    },
}
