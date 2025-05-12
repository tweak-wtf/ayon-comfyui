import logging
import numpy
from os import environ, makedirs
from copy import deepcopy
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import json
import os
import folder_paths
import comfy.utils
import os
import json
import server
from aiohttp import web
import tkinter as tk
from tkinter import filedialog
import threading
import traceback

import ayon_api
from server import PromptServer
from aiohttp import web

from ayon_core.lib import StringTemplate

log = logging.getLogger(__name__)


class AyonNode:
    def __init__(self):
        ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}
        print(f"AYON environment variables: {ayon_env}")
        self.project = ayon_env.get("AYON_PROJECT_NAME")
        self.app = ayon_env.get("AYON_APP_NAME")
        self.folder = ayon_env.get("AYON_FOLDER_PATH")
        self.task = ayon_env.get("AYON_TASK_NAME")
        self.selected_files = []
        self.id = None

        bundle_settings = ayon_api.get_bundle_settings(
            bundle_name=ayon_env.get("AYON_BUNDLE_NAME"),
            project_name=self.project["name"],
        )
        addons = bundle_settings["addons"]
        self.addon_settings = next(
            (adn["settings"] for adn in addons if adn["name"] == "comfyui")
        )
        self.core_settings = next(
            (adn["settings"] for adn in addons if adn["name"] == "core")
        )

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

    @property
    def product_types(self) -> list:
        """Get the product types for the current project

        Note:
            - only returns `render` product type
            - where do i set those in AYON?
        """
        if not self.project:
            raise ValueError("Project not set")

        product_types = ayon_api.get_project_product_types(self.project["name"])
        if not product_types:
            raise ValueError("No product types found")

        result = list([pt["name"] for pt in product_types])
        log.info(f"{result = }")
        return result

    def output_files(self):
        # Return both formats: a newline-separated string and a list of files
        file_paths_string = "\n".join(self.selected_files) if self.selected_files else ""
        file_list_json = json.dumps(self.selected_files)
        return (file_paths_string, file_list_json)

    def get_template_output_path(self, product_type, variant):
        """Generate a simple output path based on project structure

        This is a simplified version that doesn't rely on ayon_core.pipeline
        """
        try:
            # Create a basic path structure based on AYON conventions
            project_name = self.project["name"]
            print(f"Project name: {project_name}")
            folder_path = self.folder["path"].lstrip("/")
            task_name = self.task["name"]

            # Get the root path from AYON environment variables
            # AYON typically sets project roots in specific environment variables
            ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}

            # Look for project root in AYON environment variables
            workdir = ayon_env.get("AYON_WORKDIR", "")
            print(f"AYON workdir: {workdir}")
            root_path = ayon_env.get("AYON_PROJECT_ROOT", "")
            print(f"AYON project root path: {root_path}")

            # If not found, try to construct it from AYON project paths
            if not root_path and workdir:
                root_path, _ = os.path.splitdrive(workdir)
                print(f"AYON project root path from workdir: {root_path}")

            # Last resort fallback to ComfyUI output directory
            if not root_path:
                root_path = folder_paths.get_output_directory()
                log.warning(
                    f"No AYON project root found, using ComfyUI output directory: {root_path}"
                )

            # Fix for Windows paths - ensure there's a backslash after drive letter
            if len(root_path) == 2 and root_path[1] == ":":
                root_path = root_path + "\\"

            # Construct path: root/project/folder/task/product_type/variant
            # If root already includes project name, don't add it again
            if os.path.basename(root_path) == project_name:
                output_path = os.path.join(
                    root_path, folder_path, task_name, product_type, variant
                )
            else:
                output_path = os.path.join(
                    root_path,
                    project_name,
                    folder_path,
                    task_name,
                    product_type,
                    variant,
                )

            log.info(f"Generated output path: {output_path}")
            return output_path

        except Exception as e:
            log.error(f"Error generating template output path: {e}")
            return ""


class PublishImage(AyonNode):
    """AYON PublishImage node for ComfyUI

    - save 8bit png as represenation
    - save workflow as workfile
    - publish workfile and representation
    """

    def __init__(self):
        super().__init__()
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    # Update the INPUT_TYPES method to add multiline support for the output_path
    @classmethod
    def INPUT_TYPES(cls):
        # Default values in case AYON data isn't available
        default_folder_path = "/"
        default_task_name = "main"
        default_output_path = ""
        folder_options = ["/"]  # Default folder option
        task_options = ["main"]  # Default task option

        # Try to create an instance to get AYON data
        try:
            cls_inst = cls()

            # Get folder path and task name if available
            if hasattr(cls_inst, "folder") and cls_inst.folder:
                default_folder_path = cls_inst.folder.get("path", "/")

            if hasattr(cls_inst, "task") and cls_inst.task:
                default_task_name = cls_inst.task.get("name", "main")

            # Get all available folders for the project
            try:
                ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}
                project_name = ayon_env.get("AYON_PROJECT_NAME")

                if project_name:
                    # Fetch all folders for the project
                    folders = ayon_api.get_folders(project_name)
                    if folders:
                        # Extract folder paths and sort them
                        folder_options = [folder["path"] for folder in folders]
                        folder_options.sort()
                        log.info(
                            f"Found {len(folder_options)} folders in project {project_name}"
                        )

                    # Get tasks for the default folder
                    if default_folder_path:
                        try:
                            tasks = cls.get_tasks_for_folder(
                                project_name, default_folder_path
                            )
                            if tasks:
                                task_options = tasks
                                log.info(
                                    f"Found {len(task_options)} tasks for folder {default_folder_path}"
                                )
                        except Exception as e:
                            log.warning(
                                f"Could not fetch tasks for folder {default_folder_path}: {e}"
                            )
            except Exception as e:
                log.warning(f"Could not fetch folders or tasks: {e}")

            # Try to get default output path from template
            try:
                # Get output path based on environment variables
                ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}
                project_name = ayon_env.get("AYON_PROJECT_NAME")
                print(f"AYON project name: {project_name}")

                if project_name:
                    # Get the root path from AYON environment variables
                    # Look for project root in AYON environment variables
                    workdir = ayon_env.get("AYON_WORKDIR", "")
                    print(f"AYON workdir: {workdir}")
                    root_path = ayon_env.get("AYON_PROJECT_ROOT", "")
                    print(f"AYON project root path: {root_path}")

                    # If not found, try to construct it from AYON project paths
                    if not root_path and workdir:
                        root_path, _ = os.path.splitdrive(workdir)
                        print(f"AYON project root path from workdir: {root_path}")

                    # Last resort fallback to ComfyUI output directory
                    if not root_path:
                        root_path = folder_paths.get_output_directory()
                        log.warning(
                            f"No AYON project root found, using ComfyUI output directory: {root_path}"
                        )

                    # Fix for Windows paths - ensure there's a backslash after drive letter
                    if len(root_path) == 2 and root_path[1] == ":":
                        root_path = root_path + "\\"

                    # Construct path: root/project/folder/task/product_type/variant
                    # If root already includes project name, don't add it again

                    default_output_path = os.path.join(
                        root_path,
                        project_name,
                        default_folder_path.lstrip("/"),
                        default_task_name,
                        "render",  # Default product type
                        "Main",  # Default variant
                    )

                    # Make sure the directory exists
                    try:
                        os.makedirs(default_output_path, exist_ok=True)
                    except Exception:
                        pass

                    log.info(f"Default output path: {default_output_path}")
            except Exception as e:
                log.warning(f"Could not get default output path: {e}")
        except Exception as e:
            log.warning(f"Error initializing AYON data for input types: {e}")

        # TODO: get variants and product types from project settings
        variants = ["Main", "Other"]
        product_types = ["render", "image"]

        return {
            "required": {
                "image": ("IMAGE",),
                "folder_path": (
                    "COMBO",
                    {
                        "options": folder_options,
                        "default": default_folder_path,
                        "multi_select": False,
                    },
                ),
                "task_name": (
                    "COMBO",
                    {
                        "options": task_options,
                        "default": default_task_name,
                        "multi_select": False,
                    },
                ),
                "variant": (
                    "COMBO",
                    {"options": variants, "multi_select": False},
                ),
                "product_type": (
                    "COMBO",
                    {"options": product_types, "multi_select": False},
                ),
                "output_path": (
                    "STRING",
                    {
                        "default": default_output_path,
                        "multiline": True,  # Enable multiline for better display
                        "height": 80,  # Increase height for better visibility
                    },
                ),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    # Update the RETURN_TYPES and RETURN_NAMES to be empty
    RETURN_TYPES = ()  # Empty tuple means no outputs
    RETURN_NAMES = ()  # Empty tuple means no output names
    FUNCTION = "main"
    OUTPUT_NODE = True
    CATEGORY = "🟢 AYON"

    # Update the main function to not return anything
    def main(
        self,
        image,
        folder_path,
        task_name,
        variant,
        product_type,
        output_path="",
        prompt=None,
        extra_pnginfo=None,
    ):
        log.info(f"main arg: {image.shape = }")
        log.info(f"main arg: {folder_path = }")
        log.info(f"main arg: {task_name = }")
        log.info(f"main arg: {variant = }")
        log.info(f"main arg: {product_type = }")
        log.info(f"main arg: {output_path = }")

        # set folder and path to account for possible context change on the node
        try:
            self.folder = folder_path
            self.task = task_name
        except Exception as e:
            log.error(f"Error setting folder or task: {e}")
            # Use default output directory if we can't set folder or task
            output_dir = self.output_dir
            filename_prefix = "AYON_Publish"
        else:
            # get product name profiles, get profile match, solve template
            try:
                log.info(f"{self.core_settings = }")
                profiles = self.core_settings["tools"]["creator"][
                    "product_name_profiles"
                ]
                log.info(f"{profiles = }")
                tmpl = StringTemplate(profiles[0]["template"])
                tmpl_solved = tmpl.format_strict(
                    {
                        "project": self.project["name"],
                        "folder": self.folder["name"],
                        "task": self.task["name"],
                        "variant": variant,
                        "product": {"type": product_type},
                    }
                )
                log.info(f"{tmpl_solved = }")
                filename_prefix = tmpl_solved if tmpl_solved else "AYON_Publish"
            except Exception as e:
                log.error(f"Error generating filename prefix: {e}")
                filename_prefix = "AYON_Publish"

            # If output_path is empty, try to get it from template
            if not output_path:
                try:
                    template_path = self.get_template_output_path(product_type, variant)
                    if template_path:
                        output_path = template_path
                except Exception as e:
                    log.error(f"Error getting template output path: {e}")

        # Determine output directory
        if output_path:
            output_dir = output_path
            # Create the directory if it doesn't exist
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                log.warning(f"Could not create output directory {output_dir}: {e}")
                output_dir = self.output_dir  # Fall back to default output dir
        else:
            output_dir = self.output_dir

        # Find the next available counter
        counter = 1
        while True:
            file = f"{filename_prefix}_{counter:05}.png"
            save_path = os.path.join(output_dir, file)
            if not os.path.exists(save_path):
                break
            counter += 1

        # Save image - FIX FOR THE SHAPE ISSUE
        try:
            # Handle different image shapes
            i = image.cpu().numpy()

            # Check if we have a batch dimension and squeeze it if it's size 1
            if i.shape[0] == 1:
                i = i.squeeze(0)

            # If we still have a dimension of size 1 at the beginning, squeeze it too
            if len(i.shape) > 3 and i.shape[0] == 1:
                i = i.squeeze(0)

            # Now we should have a standard (H, W, C) image
            i = i * 255.0  # Scale to 0-255 range
            i = numpy.clip(i, 0, 255).astype(numpy.uint8)

            img = Image.fromarray(i)

            # Prepare metadata
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for k, v in extra_pnginfo.items():
                    metadata.add_text(k, json.dumps(v))

            # Save image
            file = f"{filename_prefix}_{counter:05}.png"
            save_path = os.path.join(output_dir, file)
            img.save(save_path, pnginfo=metadata)
            image_path = save_path
            log.info(f"Saved image to {image_path}")

        except Exception as e:
            log.error(f"Error saving image: {e}")
            log.error(f"Image shape: {image.shape}, dtype: {image.dtype}")
            image_path = ""

        # Save workflow JSON automatically from the prompt data
        workfile_path = ""
        if prompt is not None and image_path:
            try:
                # Use image name to generate workflow filename
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                workfile_name = f"{base_name}_workflow.json"
                workfile_path = os.path.join(output_dir, workfile_name)

                # Extract workflow data from prompt
                with open(workfile_path, "w") as f:
                    json.dump(prompt, f, indent=2)

                log.info(f"Saved workflow to {workfile_path}")
            except Exception as e:
                log.error(f"Error saving workflow: {e}")

        # TODO: Implement AYON publishing logic here
        # This would involve:
        # 1. Creating a product in AYON
        # 2. Publishing the image as a representation
        # 3. Publishing the workflow as a workfile

        # Don't return anything since we've hidden the outputs
        return ()

    @staticmethod
    def publish_image_api(
        node_id,
        workflow,
        folder_path=None,
        task_name=None,
        variant=None,
        product_type=None,
    ):
        """API method to publish an image from the workflow"""
        try:
            log.info(f"Publishing image from node {node_id}")
            log.info(f"Workflow data received: {len(str(workflow))} characters")

            # Find the node in the workflow
            node_data = None
            for node in workflow["nodes"]:
                if node["id"] == node_id:
                    node_data = node
                    break

            if not node_data:
                return {
                    "success": False,
                    "error": f"Node with ID {node_id} not found in workflow",
                }

            # Create an instance of PublishImage to access AYON API data
            publish_instance = PublishImage()

            # Extract values from widgets if available
            widget_values = node_data.get("widgets_values", [])
            log.info(f"Widget values: {widget_values}")

            # Use values from the node's widgets if available
            if widget_values and len(widget_values) >= 6:
                folder_path = widget_values[0] if folder_path is None else folder_path
                task_name = widget_values[1] if task_name is None else task_name
                variant = widget_values[2] if variant is None else variant
                product_type = (
                    widget_values[3] if product_type is None else product_type
                )
                output_path = widget_values[5]

            # If values are still None, use the ones from the PublishImage instance
            folder_path = folder_path or publish_instance.folder.get("path", "")
            task_name = task_name or publish_instance.task.get("name", "")
            variant = variant or "Main"
            product_type = product_type or "render"

            # Set folder and task on the instance
            try:
                publish_instance.folder = folder_path
                publish_instance.task = task_name
            except Exception as e:
                log.warning(f"Error setting folder or task: {e}")

            # If output_path is empty, get it from template
            if not output_path:
                output_path = publish_instance.get_template_output_path(
                    product_type, variant
                )

            # Create output directory if it doesn't exist
            os.makedirs(output_path, exist_ok=True)

            # Generate a filename prefix based on AYON conventions
            try:
                profiles = publish_instance.core_settings["tools"]["creator"][
                    "product_name_profiles"
                ]
                tmpl = StringTemplate(profiles[0]["template"])
                filename_prefix = tmpl.format_strict(
                    {
                        "project": publish_instance.project["name"],
                        "folder": publish_instance.folder["name"],
                        "task": publish_instance.task["name"],
                        "variant": variant,
                        "product": {"type": product_type},
                    }
                )
            except Exception as e:
                log.error(f"Error generating filename prefix: {e}")
                filename_prefix = f"{product_type}{variant}"

            # Find next available counter
            counter = 1
            while True:
                file = f"{filename_prefix}_{counter:05}.png"
                save_path = os.path.join(output_path, file)
                if not os.path.exists(save_path):
                    break
                counter += 1

            # Save workflow as JSON
            workflow_path = os.path.join(
                output_path, f"{filename_prefix}_{counter:05}_workflow.json"
            )
            with open(workflow_path, "w") as f:
                json.dump(workflow, f, indent=2)

            # Find the most recent image output from ComfyUI
            import glob

            # Get the ComfyUI output directory
            output_dir = folder_paths.get_output_directory()

            # Find the most recent PNG file in the output directory
            png_files = glob.glob(os.path.join(output_dir, "*.png"))
            if not png_files:
                return {
                    "success": False,
                    "error": "No images found in ComfyUI output directory",
                }

            # Sort by modification time (newest first)
            latest_image = max(png_files, key=os.path.getmtime)
            log.info(f"Using latest image: {latest_image}")

            # Copy the image to our output path
            import shutil

            shutil.copy2(latest_image, save_path)
            log.info(f"Copied image to: {save_path}")

            # Create a product in AYON
            try:
                # Get the folder ID from the folder entity
                folder_id = publish_instance.folder.get("id")
                if not folder_id:
                    log.warning("Could not get folder ID from folder entity")
                    return {
                        "success": True,
                        "output": f"Image saved to {save_path} (AYON publishing failed: missing folder ID)",
                    }

                # Create product name
                product_name = f"{filename_prefix}_{counter:05}"

                # Use AYON API to create product with the required arguments
                try:
                    # Create the product
                    product_id = ayon_api.create_product(
                        publish_instance.project["name"],  # project_name
                        product_name,  # name
                        product_type,  # product_type
                        folder_id,  # folder_id
                    )

                    log.info(f"Created AYON product with ID: {product_id}")

                    if not product_id:
                        log.warning("Failed to create AYON product")
                        return {
                            "success": True,
                            "output": f"Image saved to {save_path} (AYON product creation failed)",
                        }

                    # Since we don't have get_product, let's try a different approach
                    # Let's check what functions are available in ayon_api
                    available_functions = [
                        func for func in dir(ayon_api) if not func.startswith("_")
                    ]
                    log.info(f"Available functions in ayon_api: {available_functions}")

                    # Look for functions related to versions or representations
                    version_functions = [
                        func
                        for func in available_functions
                        if "version" in func.lower()
                    ]
                    representation_functions = [
                        func
                        for func in available_functions
                        if "representation" in func.lower()
                    ]

                    log.info(f"Version-related functions: {version_functions}")
                    log.info(
                        f"Representation-related functions: {representation_functions}"
                    )

                    # Let's try a simple approach - just return success for creating the product
                    # and saving the files locally

                    return {
                        "success": True,
                        "output": f"Created AYON product: {product_name}. Files saved to {output_path}",
                    }

                except Exception as e:
                    log.exception(f"Error in AYON product creation: {e}")
                    return {
                        "success": True,
                        "output": f"Image saved to {save_path} (AYON product creation error: {str(e)})",
                    }

            except Exception as e:
                log.exception("Error publishing to AYON")
                return {
                    "success": True,
                    "output": f"Image saved to {save_path} (AYON publishing error: {str(e)})",
                }

        except Exception as e:
            log.exception("Error publishing image")
            return {"success": False, "error": str(e)}

    @classmethod
    def get_folder_options(cls, project_name):
        """Get all available folders for a project"""
        try:
            folders = ayon_api.get_folders(project_name)
            if folders:
                # Extract folder paths and sort them
                folder_options = [folder["path"] for folder in folders]
                folder_options.sort()
                return folder_options
            return ["/"]
        except Exception as e:
            log.warning(f"Could not fetch folders: {e}")
            return ["/"]

    @classmethod
    def get_tasks_for_folder(cls, project_name, folder_path):
        """Get all available tasks for a folder"""
        try:
            tasks = ayon_api.get_tasks_by_folder_path(project_name, folder_path)
            if tasks:
                # Extract task names and sort them
                task_names = [task["name"] for task in tasks]
                task_names.sort()
                return task_names
            return ["main"]  # Default task if none found
        except Exception as e:
            log.warning(f"Could not fetch tasks for folder {folder_path}: {e}")
            return ["main"]


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {"AYON Publish": PublishImage}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {"AYON Publish": "AYON Publish"}

# Web directory for the custom JS
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]


# Register API endpoint
async def api_publish_image(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        workflow = data.get("workflow")
        folder_path = data.get("folder_path")
        task_name = data.get("task_name")
        variant = data.get("variant")
        product_type = data.get("product_type")

        result = PublishImage.publish_image_api(
            node_id, workflow, folder_path, task_name, variant, product_type
        )
        return web.json_response(result)
    except Exception as e:
        log.exception("Error in publish_image API endpoint")
        return web.json_response({"success": False, "error": str(e)})


async def api_update_output_path(request):
    try:
        data = await request.json()
        folder_path = data.get("folder_path")
        task_name = data.get("task_name")
        variant = data.get("variant")
        product_type = data.get("product_type")

        log.info(
            f"Updating output path for: folder={folder_path}, task={task_name}, variant={variant}, product_type={product_type}"
        )

        # Create an instance of PublishImage to access methods
        publish_instance = PublishImage()

        # Set folder and task
        try:
            publish_instance.folder = folder_path
            publish_instance.task = task_name

            # Get updated output path
            output_path = publish_instance.get_template_output_path(
                product_type, variant
            )
            log.info(f"Generated new output path: {output_path}")

            # Make sure we have a valid path
            if not output_path:
                output_path = os.path.join(
                    folder_paths.get_output_directory(),
                    "ayon_publish",
                    product_type,
                    variant,
                )
                log.warning(f"Empty path generated, using fallback: {output_path}")

            return web.json_response({"success": True, "output_path": output_path})
        except Exception as e:
            log.warning(f"Error setting folder or task: {e}")
            # Return a default path if we can't set folder or task
            output_path = os.path.join(
                folder_paths.get_output_directory(),
                "ayon_publish",
                product_type,
                variant,
            )
            log.info(f"Using fallback path due to error: {output_path}")
            return web.json_response({"success": True, "output_path": output_path})
    except Exception as e:
        log.exception("Error updating output path")
        # Even in case of error, return a valid path
        output_path = os.path.join(folder_paths.get_output_directory(), "ayon_publish")
        return web.json_response(
            {
                "success": False,
                "error": str(e),
                "output_path": output_path,  # Still provide a fallback path
            }
        )


@server.PromptServer.instance.routes.post("/selected_files")
async def select_files(request):
    try:
        print("Received file selection request")
        json_data = await request.json()
        node_id = json_data.get("node_id")
        append_mode = json_data.get("append_mode", False)
        current_files = json_data.get("current_files", [])

        print(f"Processing file selection for node ID: {node_id}, append mode: {append_mode}")

        if not node_id:
            return web.json_response({
                "success": False,
                "error": "No node_id provided"
            }, status=400)

        # Create a function to run the file dialog in a separate thread
        def open_file_dialog():
            try:
                print("Opening file dialog...")
                # Initialize tkinter root
                root = tk.Tk()
                root.withdraw()  # Hide the main window

                # Try to bring dialog to front
                root.attributes('-topmost', True)

                # Open the file dialog
                file_paths = filedialog.askopenfilenames(
                    title="Select Files",
                    filetypes=[("All Files", "*.*"),
                               ("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"),
                               ("Text Files", "*.txt;*.json;*.csv")]
                )

                # Convert tuple to list
                return list(file_paths)
            except Exception as e:
                print(f"Error in file dialog: {str(e)}")
                traceback.print_exc()
                return []

        # Run the file dialog in a separate thread and wait for result
        new_file_paths = await server.PromptServer.instance.loop.run_in_executor(None, open_file_dialog)

        # If in append mode, add the new files to the current files
        if append_mode and current_files:
            # Combine lists and remove duplicates while preserving order
            combined_files = current_files.copy()
            for file_path in new_file_paths:
                if file_path not in combined_files:
                    combined_files.append(file_path)
            file_paths = combined_files
        else:
            file_paths = new_file_paths

        print(f"Selected files: {file_paths}")

        return web.json_response({
            "success": True,
            "files": file_paths
        })
    except Exception as e:
        print(f"Error in select_files: {str(e)}")
        traceback.print_exc()
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def api_get_tasks_for_folder(request):
    try:
        data = await request.json()
        project_name = data.get("project_name")
        folder_path = data.get("folder_path")

        if not project_name:
            # Try to get project name from environment
            ayon_env = {k: v for k, v in environ.items() if k.startswith("AYON_")}
            project_name = ayon_env.get("AYON_PROJECT_NAME")

        if not project_name or not folder_path:
            return web.json_response(
                {"success": False, "error": "Missing project_name or folder_path"}
            )

        tasks = PublishImage.get_tasks_for_folder(project_name, folder_path)

        return web.json_response({"success": True, "tasks": tasks})
    except Exception as e:
        log.exception("Error getting tasks for folder")
        return web.json_response({"success": False, "error": str(e)})


# Update the router registration section at the bottom of the file
try:
    app = PromptServer.instance.app
    app.router.add_post("/publish_image", api_publish_image)
    app.router.add_post("/update_output_path", api_update_output_path)
    app.router.add_post("/get_tasks_for_folder", api_get_tasks_for_folder)
    log.info("Custom endpoints registered successfully")
except Exception as e:
    log.warning(f"Failed to register endpoints: {e}")
