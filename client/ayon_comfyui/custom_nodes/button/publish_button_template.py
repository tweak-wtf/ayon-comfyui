import server
from server import PromptServer
import logging
from aiohttp import web

logging.basicConfig(level=logging.INFO)
print("publish_button.py loaded")

class publishButton:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",)
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "open_publish"
    CATEGORY = "🟢 AYON"
    OUTPUT_NODE = True

    def open_publish(self, **kwargs):
        return ("publish button ready",)

NODE_CLASS_MAPPINGS = {"publishButton": publishButton}
NODE_DISPLAY_NAME_MAPPINGS = {"publishButton": "Publish Button Template"}
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

def run_custom_python_code():
    logging.info("Running custom Python code DIREECTLY...")
    return {"success": True, "output": "That's my Return Message"}

async def api_run_custom_code(request):
    return web.json_response(run_custom_python_code())

try:
    app = PromptServer.instance.app
    app.router.add_post("/run_custom_code", api_run_custom_code)
    logging.info("Custom endpoint /run_custom_code registered directly")
except Exception as e:
    logging.warning("Failed to register /run_custom_code endpoint: %s", e)
