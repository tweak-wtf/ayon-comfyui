# custom_nodes/saver/__init__.py

try:
    from .saver import SaveImageAndWorkfileNode
    
    NODE_CLASS_MAPPINGS = {
        "SaveImageAndWorkfileNode": SaveImageAndWorkfileNode
    }
    
    NODE_DISPLAY_NAME_MAPPINGS = {
        "SaveImageAndWorkfileNode": "Save Image + Workflow"
    }
    
    print("Successfully loaded SaveImageAndWorkfileNode")
except Exception as e:
    print(f"Error loading SaveImageAndWorkfileNode: {e}")
    import traceback
    traceback.print_exc()
    
    # Provide empty mappings to prevent further errors
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
