import ayon_api
from ayon_applications import ApplicationManager

from ayon_core.pipeline import load
from ayon_core.pipeline.load import LoadError
import asyncio
from ayon_comfyui.comfyuiclient import ComfyUIClientAsync, ComfyUIClient
from pathlib import Path
import qargparse



class comfyuiRMGB(load.LoaderPlugin):
    product_types = {
        "render2d",
        "source",
        "plate",
        "render",
        "prerender",
        "image"
    }
    representations = {"exr"}
    extensions = {"*"}

    label = "apply ComfyUI workflow"
    order = 0
    icon = "play-circle"
    color = "green"

    options_defaults = {
        "load_workflow": "D:\RMBG_api.json"
    }

    @classmethod
    def get_options(cls, *args):
        return [
            qargparse.String(
                "load_workflow",
                help="Select workflow to apply",
                default=cls.options_defaults["load_workflow"]
            ),
        ]
    
    def comfyui_open_session(self, workflowname):
        try:
            server_adress = "127.0.0.1:8188"
            self.client = ComfyUIClient(server_adress, workflowname, debug=True)
            self.client.connect()
        except:
            print('Error')
    
    async def comfyui_open_session_async(self, workflowname):
        server_adress = "127.0.0.1:8188"
        self.client = ComfyUIClientAsync(server_adress, workflowname, debug=True)
        await self.client.connect()

    def comfyui_setData(self, filepath_load, filepath_save, first_frame, last_frame):
        self.client.set_data(key='AYON_filename_load', value=filepath_load)
        self.client.set_data(key='AYON_filename_save', value=filepath_save)
        self.client.set_data(key='AYON_startframe', value=first_frame)
        self.client.set_data(key='AYON_endframe', value=last_frame)

    async def comfyui_setData_async(self, filepath_load, filepath_save, first_frame, last_frame):
        await self.client.set_data(key='AYON_filename_load', value=filepath_load)
        await self.client.set_data(key='AYON_filename_save', value=filepath_save)
        await self.client.set_data(key='AYON_startframe', value=first_frame)
        await self.client.set_data(key='AYON_endframe', value=last_frame)
    
    def make_filepaths(self, context):
        # create in- and out filepaths, compatible with OpenEXR plugin in comfy
        filepath_src = Path(self.filepath_from_context(context))
        filename_enum = filepath_src.stem.split('.')[0] + '.%04d' + filepath_src.suffix
        filepath_load = filepath_src.parent / filename_enum
        filename_save = filepath_load.stem.split('.')[0] + '_ComfyUIOutput.%04d' + filepath_src.suffix
        filepath_save = filepath_load.parent / 'comfyui_export' / filename_save
        return filepath_load, filepath_save

    def load(self, context, name, namespace, options): 
        # get context
        version_entity = context["version"]
        version_attributes = version_entity["attrib"]
        repre_entity = context["representation"]
        repre_id = repre_entity["id"]
        workflowname = options.get(
            "load_workflow", self.options_defaults["load_workflow"]
        )
        # get filepaths
        filepath_load, filepath_save = self.make_filepaths(context)
        # get frame range
        first_frame = version_attributes.get("frameStart")
        last_frame = version_attributes.get("frameEnd")
        #run comfyui session
        # self.comfyui_open_session(workflowname)
        try:
            server_adress = "127.0.0.1:8188"
            self.client = ComfyUIClient(server_adress, workflowname, debug=True)
            self.client.connect()
        except:
            print('Error')
        else:
            self.comfyui_setData(filepath_load.as_posix(), filepath_save.as_posix(), first_frame, last_frame)
            self.client.generate()
            self.client.close()