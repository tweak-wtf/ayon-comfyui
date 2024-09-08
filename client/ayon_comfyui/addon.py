import os
from ayon_core.addon import AYONAddon, IPluginPaths, IHostAddon

from .version import __version__


ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))
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

    def get_plugin_paths(self):
        return {
            "actions": [os.path.join(ADDON_ROOT, "plugins", "actions")],
        }
