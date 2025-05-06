# custom_nodes/saver/saver.py

from PIL import Image
from PIL.PngImagePlugin import PngInfo
import numpy as np
import os
import json
import folder_paths
import comfy.utils

class SaveImageAndWorkfileNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "ComfyUI"}),
                "output_path": ("STRING", {"default": ""})
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("image_path", "workflow_path")
    FUNCTION = "save_images_and_workfile"
    CATEGORY = "image"
    OUTPUT_NODE = True  # This is the key addition to make it a valid output node

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    def save_images_and_workfile(self, images, filename_prefix="ComfyUI", output_path="", prompt=None, extra_pnginfo=None):
        # Determine output directory
        output_dir = output_path if output_path and os.path.isdir(output_path) else self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Find the next available counter
        counter = 1
        while True:
            file = f"{filename_prefix}_{counter:05}.png"
            save_path = os.path.join(output_dir, file)
            if not os.path.exists(save_path):
                break
            counter += 1
        
        image_paths = []
        
        # Save images
        for image in images:
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

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
            image_paths.append(save_path)
            counter += 1

        # Save workflow JSON automatically from the prompt data
        workfile_path = ""
        if prompt is not None:
            try:
                # Use first image name to generate workflow filename
                base_name = os.path.splitext(os.path.basename(image_paths[0]))[0]
                workfile_name = f"{base_name}_workflow.json"
                workfile_path = os.path.join(output_dir, workfile_name)

                # Extract workflow data from prompt
                with open(workfile_path, 'w') as f:
                    json.dump(prompt, f, indent=2)
                    
                print(f"[SaveImageAndWorkfile] Saved workflow to {workfile_path}")
            except Exception as e:
                print(f"[SaveImageAndWorkfile] Error saving workflow: {e}")

        # Return paths of first saved image and workfile
        return (image_paths[0] if image_paths else "", workfile_path)
