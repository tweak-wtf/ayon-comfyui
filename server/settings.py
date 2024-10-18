from pathlib import Path
from typing import Literal, TYPE_CHECKING

from pydantic import Field, validator

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    MultiplatformPathModel,
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


class CustomNodeSettings(RepositorySettings):
    extra_dependencies: list[str] = SettingsField(
        default_factory=list,
        description="Extra python dependencies to install.",
        title="Extra Dependencies",
    )


class ComfyUIExtraModelSettings(BaseSettingsModel):
    enabled: bool = SettingsField(default=True, description="Enable this extra model.")
    template: str = SettingsField(
        default="",
        title="Directory Template",
        description="Where to load extra models from.",
    )
    copy_to_base: bool = SettingsField(
        default=False,
        title="Copy to Base",
        description="Copy all found extra models to their respective ComfyUI base directory.",
    )


class ComfyUIGeneralSettings(BaseSettingsModel):
    use_cpu: bool = SettingsField(
        default=False, title="Use CPU", description="Use only CPU."
    )
    checkpoints: ComfyUIExtraModelSettings = SettingsField(
        default_factory=ComfyUIExtraModelSettings,
    )
    models: ComfyUIExtraModelSettings = SettingsField(
        default_factory=ComfyUIExtraModelSettings,
    )


class ComfyUIRepositorySettings(BaseSettingsModel):
    base_template: str = SettingsField(
        default="",
        title="Repository Root Template",
        description="Where to clone the ComfyUI repository to.",
    )
    base: RepositorySettings = SettingsField(
        default_factory=RepositorySettings,
        description="Base Repository Settings.",
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

    repositories: ComfyUIRepositorySettings = SettingsField(
        default_factory=ComfyUIRepositorySettings,
        title="Repository Settings",
        description="Git Repository Settings.",
    )
    general: ComfyUIGeneralSettings = SettingsField(
        default_factory=ComfyUIGeneralSettings,
        title="General Settings",
        description="General settings.",
    )
    caching: ComfyUICachingSettings = SettingsField(
        default_factory=ComfyUICachingSettings,
        title="Caching Settings",
        description="Can be used in air gapped scenarios.",
    )


DEFAULT_VALUES = {
    "repositories": {
        "base_template": "{root[work]}/{project[name]}/comfyui",
        "base": {
            "url": "https://github.com/comfyanonymous/ComfyUI.git",
            "tag": "v0.2.2",
        },
        "plugins": [{"url": "https://github.com/ltdrdata/ComfyUI-Manager.git"}],
    },
}
