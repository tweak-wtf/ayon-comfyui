import folder_paths
from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

class HelloWorldButton:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
        }

    RETURN_TYPES = ()
    FUNCTION = "do_nothing"
    OUTPUT_NODE = True  # allows UI interaction without outputs
    CATEGORY = "Custom"

    def do_nothing(self):
        return ()

NODE_CLASS_MAPPINGS["HelloWorldButton"] = HelloWorldButton
NODE_DISPLAY_NAME_MAPPINGS["HelloWorldButton"] = "🟢 Hello Button"
