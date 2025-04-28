import logging
import numpy
from os import environ
from copy import deepcopy
from pathlib import Path
from PIL import Image

import ayon_api

log = logging.getLogger(__name__)


class AyonNode:
    def __init__(self):
        ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}
        self.project = ayon_env.get("AYON_PROJECT_NAME")
        log.info(f"{self.project = }")
        self.app = ayon_env.get("AYON_APP_NAME")
        log.info(f"{self.app = }")
        self.folder = ayon_env.get("AYON_FOLDER_PATH")
        log.info(f"{self.folder = }")
        self.task = ayon_env.get("AYON_TASK_NAME")
        log.info(f"{self.task = }")

    @property
    def app(self) -> dict:
        if not self.__app:
            raise ValueError("App not set")
        return self.__app

    @app.setter
    def app(self, name: str):
        if "/" not in name:
            raise ValueError("App name must be in the format 'app_name/version'")
        app_splits = name.split("/")
        self.__app = {
            "name": app_splits[0],
            "version": app_splits[1],
        }

    @property
    def app_name(self) -> str:
        if not self.app:
            raise ValueError("App not set")
        return self.app.split("/")[0]

    @property
    def app_version(self) -> str:
        if not self.app:
            raise ValueError("App not set")
        return self.app.split("/")[1]

    @property
    def folder(self) -> dict:
        if not self.__folder:
            raise ValueError("Folder not set")
        return self.__folder

    @folder.setter
    def folder(self, path: str):
        if not self.project:
            raise ValueError("Project not set")

        folder_entity = ayon_api.get_folder_by_path(self.project["name"], path)
        if not folder_entity:
            raise ValueError(f"Folder {path} not found")

        self.__folder = folder_entity

    @property
    def project(self) -> dict:
        if not self.__project:
            raise ValueError("Project not set")
        return self.__project

    @project.setter
    def project(self, name: str):
        project = ayon_api.get_project(name)
        if not project:
            raise ValueError(f"Project {name} not found")
        
        self.__project = project

    @property
    def task(self) -> dict:
        if not self.__task:
            raise ValueError("Task not set")
        return self.__task
    
    @task.setter
    def task(self, name: str):
        if not self.project:
            raise ValueError("Project not set")
    
        if not self.folder:
            raise ValueError("Folder not set")

        task = ayon_api.get_task_by_folder_path(
            self.project["name"],
            self.folder["path"],
            name,
        )
        if not task:
            raise ValueError(f"Task {name} not found")

        self.__task = task

class PublishImage(AyonNode):
    """AYON PublishImage node for ComfyUI

    - save 8bit png as represenation
    - save workflow as workfile
    - publish workfile and representation
    """

    def __init__(self):
        super().__init__()

    @classmethod
    def INPUT_TYPES(cls):
        cls_inst = cls()
        # TODO: get variants and product types from project settings
        variants = ["Main", "Other"]
        product_types = ["render", "image"]
        return {
            "required": {
                "image": ("IMAGE",),
                # "save_workfile": ("BOOLEAN", {"default": True}),
                "folder_path": ("STRING", {"default": cls_inst.folder["path"]}),
                "task_name": ("STRING", {"default": cls_inst.task["name"]}),
                "variant": (
                    "COMBO",
                    {"options": variants, "multi_select": False},
                ),
                "product_type": (
                    "COMBO",
                    {"options": product_types, "multi_select": False},
                ),
            }
        }

    RETURN_TYPES = ()
    # RETURN_NAMES = ("image_output_name",)
    FUNCTION = "main"
    OUTPUT_NODE = True
    CATEGORY = "👀"

    def main(self, image, folder_path, task_name, variant, product_type):
        log.info(f"{image = }")


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {"PublishImage": PublishImage}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {"PublishImage": "PublishImage"}
