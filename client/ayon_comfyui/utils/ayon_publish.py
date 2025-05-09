import os
import json
import shutil
from typing import Dict, Any, Optional
import ayon_api
import uuid

# Currently only for single file publish
# TODO add sequence handling for a list of files. Should group sequences as single representation
# TODO  add multiple representations for one version
def debug_print_response(response, context: str = ""):
    """Print detailed response information for debugging."""
    print(f"\n[DEBUG] {context} Response:")
    print(f"Status Code: {response.status_code}")
    print("Headers:")
    for k, v in response.headers.items():
        print(f"  {k}: {v}")
    print("Body:")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)

def get_or_create_product(
    project_name: str, folder_id: str, product_name: str, product_type: str
) -> Dict[str, Any]:
    """Get existing product or create new one with detailed debugging."""
    print(f"\n[PRODUCT] Looking for product '{product_name}' in folder {folder_id}")
    try:
        product = ayon_api.get_product_by_name(
            project_name=project_name, product_name=product_name, folder_id=folder_id
        )

        if product:
            print(f"[PRODUCT] Found existing product:")
            print(json.dumps(product, indent=2))
            return product

        print(f"[PRODUCT] Creating new product '{product_name}'")
        product_data = {
            "name": product_name,
            "productType": product_type.lower(),
            "folderId": folder_id,
            "data": {"description": "Automatically created product"},
        }
        print("[PRODUCT] Creation payload:")
        print(json.dumps(product_data, indent=2))

        product = ayon_api.create_product(project_name, **product_data)
        print(f"[PRODUCT] Created new product successfully")
        return product

    except Exception as e:
        print(f"[ERROR] Product operation failed: {str(e)}")
        raise

def get_next_version(project_name: str, product_id: str) -> int:
    """Get next version number with detailed debugging."""
    print(f"\n[VERSION] Getting versions for product {product_id}")
    try:
        versions = ayon_api.get_versions(project_name, product_ids=[product_id])

        if versions:
            version_numbers = [v["version"] for v in versions]
            next_version = max(version_numbers) + 1
            print(f"[VERSION] Found versions: {version_numbers}")
        else:
            next_version = 1
            print("[VERSION] No existing versions found")

        print(f"[VERSION] Next version will be: {next_version}")
        return next_version

    except Exception as e:
        print(f"[ERROR] Version check failed: {str(e)}")
        return 1

def get_project_anatomy(project_name: str) -> Dict[str, Any]:
    """Get project anatomy data."""
    print(f"\n[ANATOMY] Fetching anatomy for project {project_name}")
    try:
        project = ayon_api.get_project(project_name)
        if not project:
            raise ValueError(f"Project not found: {project_name}")
        print(project)
        anatomy = project.get("config", {})
        if not anatomy:
            raise ValueError("No anatomy data found in project")

        print("[ANATOMY] Anatomy data retrieved")
        return anatomy
    except Exception as e:
        print(f"[ERROR] Failed to get anatomy data: {str(e)}")
        raise

def construct_publish_path(
    file_path: str,
    project_name: str,
    folder_path: str,
    product_name: str,
    product_type: str,
    representation_name: str,
    version: int,
    anatomy_data: Dict[str, Any],
    udim: str = "",
    frame: str = "",
    output: str = "",
) -> str:
    """Construct publish path using anatomy templates, handling empty optional fields."""
    print("\n[PATH] Constructing publish path")
    try:
        # Get roots
        roots = anatomy_data.get("roots", {})
        publish_root = roots.get("publish", roots.get("default"))
        if not publish_root:
            raise ValueError("No publish root found in anatomy data")

        print(f"[PATH] Publish root: {publish_root}")

        # Get templates
        templates = anatomy_data.get("templates", {}).get("publish", {})
        if not templates:
            raise ValueError("No publish templates found in anatomy data")

        # Find appropriate template
        template = templates.get("ComfyUi")
        if not template:
            raise ValueError(f"No template found for product type {product_type}")

        print(f"[PATH] Using template: {template}")
        directory_template = template.get("directory", "")
        file_template = template.get("file", "")
        print(f"FileTemplate {file_template}")
        # Prepare template data
        parts = folder_path.strip("/").split("/")

        if len(parts) == 2:
            hierarchy, folder_name = parts[0], parts[1]
        elif len(parts) == 1:
            hierarchy, folder_name = parts[0], ""
        else:
            hierarchy, folder_name = "", ""

        folder_name = os.path.basename(folder_path.rstrip("/"))

        template_data = {
            "root": {"publish": publish_root.get("windows")},
            "project": {
                "name": project_name,
                "code": project_name[:3],
            },
            "folder": {"name": folder_name, "path": folder_path},
            "hierarchy": hierarchy,
            "product": {"name": product_name, "type": product_type},
            "version": f"v{version:03d}",
            "frame": frame,
            "udim": udim,
            "representation": representation_name,
            "ext": representation_name,
            "originalBasename": os.path.splitext(os.path.basename(file_path))[0],
            "output": "",
            "exr": "jpg",
        }
        print(file_template)
        # Clean up empty optional fields in the filename template
        if not udim:
            file_template = file_template.replace("<_{udim}>", "")
        if not frame:
            file_template = file_template.replace("<.{frame}>", "")
        if not output:
            file_template = file_template.replace("<_{output}>", "")
        print(file_template)
        # Remove any double underscores or trailing/leading underscores
        file_template = file_template.replace("__", "_").strip("_")

        print(f"[PATH] Final file template: {file_template}")

        # Format paths
        publish_dir = directory_template.format(**template_data)
        filename = file_template.format(**template_data)

        # Clean up the filename (remove double underscores and empty sections)
        filename = filename.replace("__", "_").strip("_")

        # Ensure we don't have double extensions
        if filename.endswith(f".{representation_name}.{representation_name}"):
            filename = filename.replace(
                f".{representation_name}.{representation_name}",
                f".{representation_name}",
            )

        publish_path = os.path.normpath(os.path.join(publish_dir, filename))

        print(f"[PATH] Publish directory: {publish_dir}")
        print(f"[PATH] Filename: {filename}")
        print(f"[PATH] Full publish path: {publish_path}")

        # Create directory structure
        os.makedirs(publish_dir, exist_ok=True)
        print("[PATH] Directory structure created")

        return publish_path

    except Exception as e:
        print(f"[ERROR] Failed to construct publish path: {str(e)}")
        raise


def publish_image_to_ayon(
    file_path: str,
    project_name: str,
    folder_path: str,
    product_name: str,
    product_type: str = "image",
    representation_name: str = "png",
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish an image using AYON's anatomy templates and project roots."""
    print(f"\n=== Starting publish process ===")
    print(f"[FILE] Input file: {file_path}")

    # Validate file exists
    if not os.path.exists(file_path):
        raise ValueError(f"[ERROR] File does not exist: {file_path}")
    print("[FILE] Validation passed")

    # Initialize connection
    ayon_api.init_service()
    print("[CONNECTION] Initialized API connection")

    try:
        # Get folder
        print(f"\n[FOLDER] Looking for folder: {folder_path}")
        folder = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder:
            raise ValueError(f"[ERROR] Folder not found: {folder_path}")
        folder_id = folder["id"]
        print(f"[FOLDER] Found folder ID: {folder_id}")

        # Get or create product
        product = get_or_create_product(
            project_name, folder_id, product_name, product_type
        )
        product_id = product["id"]

        # Get next version
        next_version = get_next_version(project_name, product_id)

        # Get project anatomy
        anatomy_data = get_project_anatomy(project_name)

        # Construct publish path
        publish_path = construct_publish_path(
            file_path=file_path,
            project_name=project_name,
            folder_path=folder_path,
            product_name=product_name,
            product_type=product_type,
            representation_name=representation_name,
            version=next_version,
            anatomy_data=anatomy_data,
        )

        # Copy file to publish location
        shutil.copy2(file_path, publish_path)
        print(f"[FILE] Published to: {publish_path}")

        # Get current user
        author = os.getenv("USER")
        if not author:
            author = "system"

        # Create version
        version_data = {
            "version": next_version,
            "product_id": product_id,
            "author": author,
            "status": "Pending review",
            "attrib": {
                "fps": 24,
                "resolutionWidth": 1920,
                "resolutionHeight": 1080,
            },
            "data": {"comment": description or ""},
        }
        print("[VERSION] Creation payload:")
        print(json.dumps(version_data, indent=2))

        version = ayon_api.create_version(project_name, **version_data)
        version_id = version
        print(f"[VERSION] Created successfully with ID: {version_id}")

        # Create representation
        print(f"\n[REPRESENTATION] Creating representation '{representation_name}'")
        print(os.path.basename(publish_path))
        base_name, pubdir = os.path.basename(publish_path), os.path.dirname(
            publish_path
        )
        print(base_name.split(".")[0])
        print(pubdir)
        print(representation_name)
        rep_data = {
            "name": representation_name,
            "version_id": version_id,
            "files": [
                {
                    "id": uuid.uuid1().hex,
                    "name": os.path.basename(publish_path),
                    "path": publish_path,
                    "size": os.path.getsize(publish_path),
                }
            ],
            "tags": ["review"],
            "data": {
                "colorspace": "sRGB",
                "originalBasename": os.path.basename(file_path),
            },
        }
        print(rep_data)
        print("[REPRESENTATION] Creation payload:")
        print(json.dumps(rep_data, indent=2))

        representation = ayon_api.create_representation(project_name, **rep_data)
        representation_id = representation
        print(f"[REPRESENTATION] Created successfully with ID: {representation_id}")

        review_data = {
            "version_id": version_id,
            "filepath": publish_path,
        }
        ayon_api.upload_reviewable(project_name, **review_data)

        return {
            "status": "success",
            "product_id": product_id,
            "version_id": version_id,
            "representation_id": representation_id,
            "path": publish_path,
            "version": next_version,
        }

    except Exception as e:
        print(f"\n[ERROR] Publish failed: {str(e)}")
        raise

# EXAMPLE USAGE
try:
    print("[INIT] Initializing AYON connection")
    ayon_api.init_service(
        server_url=os.getenv("AYON_SERVER_URL"), token=os.getenv("AYON_API_KEY")
    )
    print("\n[START] Beginning publish process")
    result = publish_image_to_ayon(
        file_path=r"C:\Users\alex.szabados\Pictures\download.jpg",
        project_name="alex_playground",
        folder_path="/shots/sh0100",
        product_name="test_render",
        product_type="render",
        representation_name="jpg",
        description="Test publish with anatomy",
    )
    print("\n=== Publish Successful ===")
    print(json.dumps(result, indent=2))
except Exception as e:
    print("\n=== Publish Failed ===")
    print(f"Error: {str(e)}")
