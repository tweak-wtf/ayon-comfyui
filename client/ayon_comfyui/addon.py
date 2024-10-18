from pathlib import Path
from ayon_core.addon import AYONAddon, IPluginPaths, IHostAddon

from .version import __version__


ADDON_ROOT = Path(__file__).parent.resolve()
ADDON_NAME = "comfyui"
ADDON_LABEL = "ComfyUI"
ADDON_VERSION = __version__


class ComfyUIAddon(AYONAddon, IPluginPaths, IHostAddon):
    name = host_name = ADDON_NAME
    label = ADDON_LABEL
    version = __version__

    def initialize(self, settings):
        """Initialization of module."""
        self.enabled = True

    def get_launch_hook_paths(self, app):
        self.log.debug(f"{app = }")
        return [
            (ADDON_ROOT / "hooks").as_posix(),
        ]

    def get_plugin_paths(self):
        return {
            "actions": [
                (ADDON_ROOT / "plugins" / "actions").as_posix(),
            ],
        }
