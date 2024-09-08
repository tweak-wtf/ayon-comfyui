from typing import Literal, TYPE_CHECKING

from pydantic import Field, validator

from ayon_server.settings import BaseSettingsModel, SettingsField


class RepositorySettings(BaseSettingsModel):
    url: str = SettingsField(default="", description="Repository URL.")
    tag: str = SettingsField(
        default="", description="Repository tag. Leave empty for latest."
    )


class ComfyUIRepositorySettings(RepositorySettings):
    root: str = SettingsField(
        default="", description="Repository root directory template."
    )


class ComfyUISettings(BaseSettingsModel):
    """ComfyUI addon settings."""

    use_cpu: bool = SettingsField(
        default=True, title="Use CPU", description="Use only CPU."
    )
    # C:/Users/tweak/Downloads/ComfyUI_Workshop_files/ComfyUI_windows_portable_workshop/ComfyUI/models/checkpoints
    checkpoints_dir: str = SettingsField(
        default="",
        title="Checkpoints Directory",
        description="Directory to copy checkpoints from.",
    )
    repo: ComfyUIRepositorySettings = SettingsField(
        default_factory=ComfyUIRepositorySettings,
        title="Repository",
        description="Where to pull ComfyUI sources from and to.",
    )
    plugins: list[RepositorySettings] = SettingsField(
        default_factory=list[RepositorySettings],
        description="Custom plugin repositories to load.",
    )


DEFAULT_VALUES = {
    "repo": {
        "tag": "v0.2.2",
        "url": "https://github.com/comfyanonymous/ComfyUI.git",
        "root": "{root[work]}/{project[name]}/comfyui",
    },
    "plugins": [{"tag": "", "url": "https://github.com/ltdrdata/ComfyUI-Manager.git"}],
    "use_cpu": False,
}
