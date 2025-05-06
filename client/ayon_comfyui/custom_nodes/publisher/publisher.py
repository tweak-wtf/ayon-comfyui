import os

class SaveGroupNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "save_dir": ("STRING", {"default": "outputs/"}),
                "filename": ("STRING", {"default": "my_render"}),
                "save_workfile": ("BOOLEAN", {"default": True}),
                "save_image": ("BOOLEAN", {"default": True}),
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "execute"
    CATEGORY = "Custom/SaveTools"

    #def execute(self, save_dir, filename, save_workfile, save_image, image):
    #    full_path = os.path.join(save_dir, filename)
#
    #    if save_workfile:
    #        json_path = full_path + ".json"
    #        nodes.save_workflow(json_path)  # or your own logic
#
    #    if save_image:
    #        image_path = full_path + ".png"
    #        image.save(image_path)  # or use ComfyUI's save node utils
#
    #    return ()
