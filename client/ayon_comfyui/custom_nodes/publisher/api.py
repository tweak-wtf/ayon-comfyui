import json
from urllib import request, error

# This must match a model you have in ComfyUI's models/checkpoints directory!
CKPT_NAME = "v1-5-pruned-emaonly-fp16.safetensors"
prompt = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 8,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 5,
            "steps": 20
        }
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": CKPT_NAME
        }
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "batch_size": 1,
            "height": 512,
            "width": 512
        }
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "masterpiece best quality man"
        }
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "bad hands"
        }
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        }
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "ComfyUI",
            "images": ["8", 0]
        }
    }
}

def queue_prompt(prompt_dict):
    url = "http://127.0.0.1:8188/prompt"
    payload = {"prompt": prompt_dict}
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")

    try:
        response = request.urlopen(req)
        print("[INFO] Prompt queued successfully!")
        print(response.read().decode('utf-8'))
    except error.HTTPError as e:
        print("[ERROR] HTTP Error:", e.code, e.reason)
        print(e.read().decode('utf-8'))
    except error.URLError as e:
        print("[ERROR] URL Error:", e.reason)

queue_prompt(prompt)
