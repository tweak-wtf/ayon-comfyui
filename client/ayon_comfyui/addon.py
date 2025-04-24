from pathlib import Path
from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__


ADDON_ROOT = Path(__file__).parent
ADDON_NAME = "comfyui"
ADDON_LABEL = "ComfyUI"
ADDON_VERSION = __version__


class ComfyUIAddon(AYONAddon, IHostAddon):
    name = host_name = ADDON_NAME
    label = ADDON_LABEL
    version = __version__

    def initialize(self, settings):
        """Initialization of module."""
        self.enabled = True

    def get_launch_hook_paths(self, app):
        return [
            (ADDON_ROOT / "hooks").as_posix(),
        ]

    def get_workfile_extension(self) -> None:
        return [".ps1"]
