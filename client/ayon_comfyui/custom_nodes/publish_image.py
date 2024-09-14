import numpy
from PIL import Image


class PublishImage:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image": ("IMAGE")}}

    RETURN_TYPES = ()
    # RETURN_NAMES = ("image_output_name",)

    FUNCTION = "main"

    OUTPUT_NODE = True

    CATEGORY = "👀"

    def check_lazy_status(self, image):
        return ["image"]

    def main(self, image):
        # do some processing on the image, in this example I just invert it
        # image = numpy.array(image)
        image = numpy.array(image)
        img = Image.fromarray(image)
        img.save("image.jpg")
        # return ()

    """
        The node will always be re executed if any of the inputs change but
        this method can be used to force the node to execute again even when the inputs don't change.
        You can make this node return a number or a string. This value will be compared to the one returned the last time the node was
        executed, if it is different the node will be executed again.
        This method is used in the core repo for the LoadImage node where they return the image hash as a string, if the image hash
        changes between executions the LoadImage node is executed again.
    """
    # @classmethod
    # def IS_CHANGED(s, image, string_field, int_field, float_field, print_to_screen):
    #    return ""


# Set the web directory, any .js file in that directory will be loaded by the frontend as a frontend extension
# WEB_DIRECTORY = "./somejs"


# Add custom API routes, using router
from aiohttp import web
from server import PromptServer


@PromptServer.instance.routes.get("/hello")
async def get_hello(request):
    return web.json_response("hello")


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {"PublishImage": PublishImage}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {"PublishImage": "PublishImage"}
