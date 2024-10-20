from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import AddonSettings, DEFAULT_VALUES


class ComfyUIServerAddon(BaseServerAddon):
    settings_model: Type[AddonSettings] = AddonSettings

    def initialize(self):
        pass

    async def setup(self):
        pass

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
