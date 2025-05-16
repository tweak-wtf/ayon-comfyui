import os
import json
import shutil
import re
from typing import Dict, Any, Optional, List, Tuple, Union
import ayon_api
import uuid


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
            "product_type": product_type.lower(),
            "folder_id": folder_id,
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
        output: str = "", ) -> str:
    """Construct publish path using anatomy templates, handling empty optional fields."""
    print("\n[PATH] Constructing publish path")
    try:
        # Get roots
        roots = anatomy_data.get("roots", {})
        print(f"[PATH] Roots: {roots}")
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
            "output": output,
            "exr": "jpg",
        }
        print(file_template)

        # Clean up empty optional fields in the filename template
        # FIXED: Replace the placeholder patterns with empty strings or actual values
        if not udim:
            file_template = file_template.replace("<_{udim}>", "")
        else:
            file_template = file_template.replace("<_{udim}>", f"_{udim}")

        if not frame:
            file_template = file_template.replace("<.{frame}>", "")
        else:
            file_template = file_template.replace("<.{frame}>", f".{frame}")

        if not output:
            file_template = file_template.replace("<_{output}>", "")
        else:
            file_template = file_template.replace("<_{output}>", f"_{output}")

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


def detect_sequence(file_paths: List[str]) -> Dict[str, List[str]]:
    """
    Detect sequences in a list of file paths.

    Returns a dictionary where:
    - Keys are sequence patterns (or single files if not part of a sequence)
    - Values are lists of files in that sequence
    """
    print(f"\n[SEQUENCE] Analyzing {len(file_paths)} files for sequences")

    # Regular expression to detect frame numbers in filenames
    frame_pattern = re.compile(r'(.+?)(\d+)(\.\w+)$')

    # Group files by their sequence pattern
    sequences = {}

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        match = frame_pattern.match(filename)

        if match:
            # This file appears to be part of a sequence
            prefix, frame_num, suffix = match.groups()
            pattern = f"{prefix}##{suffix}"

            if pattern not in sequences:
                sequences[pattern] = []

            sequences[pattern].append(file_path)
        else:
            # Not part of a sequence, treat as individual file
            sequences[filename] = [file_path]

    # Sort each sequence by frame number
    for pattern, files in sequences.items():
        if len(files) > 1:  # Only sort actual sequences
            files.sort(key=lambda f: int(re.search(r'(\d+)(\.\w+)$', os.path.basename(f)).group(1)))

    # Print sequence detection results
    for pattern, files in sequences.items():
        if len(files) > 1:
            print(f"[SEQUENCE] Detected sequence '{pattern}' with {len(files)} frames")
        else:
            print(f"[SEQUENCE] Single file: {os.path.basename(files[0])}")

    return sequences


def extract_frame_info(file_path: str) -> Tuple[Optional[str], Optional[int]]:
    """Extract frame number and base name from a file path."""
    filename = os.path.basename(file_path)
    match = re.search(r'(.+?)(\d+)(\.\w+)$', filename)

    if match:
        prefix, frame_num, suffix = match.groups()
        return prefix, int(frame_num)

    return None, None


def create_representation(
        project_name: str,
        version_id: str,
        representation_name: str,
        files: List[str],
        is_sequence: bool = False,
        original_basename: Optional[str] = None,
        tags: List[str] = None,
        colorspace: str = "sRGB",
) -> str:
    """Create a representation with the given files."""
    print(f"\n[REPRESENTATION] Creating representation '{representation_name}'")

    file_entries = []
    for file_path in files:
        file_entries.append({
            "id": uuid.uuid1().hex,
            "name": os.path.basename(file_path),
            "path": file_path,
            "size": os.path.getsize(file_path),
        })

    rep_data = {
        "name": representation_name,
        "version_id": version_id,
        "files": file_entries,
        "tags": tags or ["review"],
        "data": {
            "colorspace": colorspace,
            "originalBasename": original_basename or os.path.basename(files[0]),
            "isSequence": is_sequence
        },
    }

    print("[REPRESENTATION] Creation payload:")
    print(json.dumps(rep_data, indent=2))

    representation = ayon_api.create_representation(project_name, **rep_data)
    representation_id = representation
    print(f"[REPRESENTATION] Created successfully with ID: {representation_id}")

    return representation_id


def publish_to_ayon(
        file_paths: Union[str, List[str]],
        project_name: str,
        folder_path: str,
        product_name: str,
        product_type: str = "image",
        representation_names: Optional[List[str]] = None,
        description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish files to AYON with support for sequences and multiple representations.

    Args:
        file_paths: Single file path or list of file paths to publish
        project_name: AYON project name
        folder_path: AYON folder path
        product_name: Name of the product to create or use
        product_type: Type of product (default: "image")
        representation_names: List of representation names (derived from file extensions if None)
        description: Optional description for the version

    Returns:
        Dictionary with publish results
    """
    print(f"\n=== Starting publish process ===")

    # Convert single file path to list for consistent handling
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    # Validate files exist
    for file_path in file_paths:
        if not os.path.exists(file_path):
            raise ValueError(f"[ERROR] File does not exist: {file_path}")
    print(f"[FILE] Validation passed for {len(file_paths)} files")

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
        print(f"[PRODUCT] Found product ID: {product_id}")
        # Get next version
        next_version = get_next_version(project_name, product_id)

        # Get project anatomy
        anatomy_data = get_project_anatomy(project_name)

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

        # Detect sequences in the files
        sequences = detect_sequence(file_paths)

        # If representation_names not provided, derive from file extensions
        if not representation_names:
            representation_names = []
            for file_path in file_paths:
                ext = os.path.splitext(file_path)[1].lstrip('.')
                if ext not in representation_names:
                    representation_names.append(ext)
        # Process each sequence or single file
        representation_ids = []
        publish_paths = []

        for pattern, files in sequences.items():
            is_sequence = len(files) > 1

            # Determine representation name from file extension
            file_ext = os.path.splitext(files[0])[1].lstrip('.')
            representation_name = file_ext.lower()

            # Handle sequence publishing
            if is_sequence:
                # Get frame numbers for sequence
                first_file = files[0]
                _, first_frame = extract_frame_info(first_file)
                _, last_frame = extract_frame_info(files[-1])
                frame_str = f"{first_frame}-{last_frame}"

                # Create a directory for the sequence
                sequence_publish_paths = []

                for file_path in files:
                    _, frame_num = extract_frame_info(file_path)
                    frame = f"{frame_num:04d}"

                    # Construct publish path for each frame
                    publish_path = construct_publish_path(
                        file_path=file_path,
                        project_name=project_name,
                        folder_path=folder_path,
                        product_name=product_name,
                        product_type=product_type,
                        representation_name=representation_name,
                        version=next_version,
                        anatomy_data=anatomy_data,
                        frame=frame
                    )

                    # Copy file to publish location
                    shutil.copy2(file_path, publish_path)
                    print(f"[FILE] Published to: {publish_path}")
                    sequence_publish_paths.append(publish_path)

                # Create representation for the sequence
                rep_id = create_representation(
                    project_name=project_name,
                    version_id=version_id,
                    representation_name=representation_name,
                    files=sequence_publish_paths,
                    is_sequence=True,
                    original_basename=os.path.splitext(os.path.basename(files[0]))[0],
                    tags=["review", "sequence"]
                )
                representation_ids.append(rep_id)
                publish_paths.extend(sequence_publish_paths)

                # Upload first frame as reviewable
                review_data = {
                    "version_id": version_id,
                    "filepath": sequence_publish_paths[0],
                }
                ayon_api.upload_reviewable(project_name, **review_data)

            else:
                # Single file publishing
                file_path = files[0]

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

                # Create representation
                rep_id = create_representation(
                    project_name=project_name,
                    version_id=version_id,
                    representation_name=representation_name,
                    files=[publish_path],
                    is_sequence=False,
                    original_basename=os.path.splitext(os.path.basename(file_path))[0]
                )
                representation_ids.append(rep_id)
                publish_paths.append(publish_path)

                # Upload reviewable
                review_data = {
                    "version_id": version_id,
                    "filepath": publish_path,
                }
                ayon_api.upload_reviewable(project_name, **review_data)

        return {
            "status": "success",
            "product_id": product_id,
            "version_id": version_id,
            "representation_ids": representation_ids,
            "paths": publish_paths,
            "version": next_version,
        }

    except Exception as e:
        print(f"\n[ERROR] Publish failed: {str(e)}")
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
    """
    Legacy function for publishing a single image.
    Now uses the more general publish_to_ayon function.
    """
    result = publish_to_ayon(
        file_paths=file_path,
        project_name=project_name,
        folder_path=folder_path,
        product_name=product_name,
        product_type=product_type,
        representation_names=[representation_name],
        description=description
    )

    # Convert to legacy format for backward compatibility
    legacy_result = {
        "status": result["status"],
        "product_id": result["product_id"],
        "version_id": result["version_id"],
        "representation_id": result["representation_ids"][0] if result["representation_ids"] else None,
        "path": result["paths"][0] if result["paths"] else None,
        "version": result["version"]
    }

    return legacy_result


    # EXAMPLE USAGE

try:
    print("[INIT] Initializing AYON connection")
    ayon_api.init_service(
        server_url=os.getenv("AYON_SERVER_URL"), token=os.getenv("AYON_API_KEY")
    )
    # Example 1: Single file publish (legacy method)
    print("\n[START] Beginning single file publish process")
    result = publish_image_to_ayon(
        file_path=r"C:\Users\alex.szabados\Pictures\download.jpg",
        project_name="demo_Big_Episodic",
        folder_path="/sq/sh0100",
        product_name="test_render",
        product_type="render",
        representation_name="jpg",
        description="Test publish with anatomy",
    )
    print("\n=== Single File Publish Successful ===")
    print(json.dumps(result, indent=2))
except Exception as e:
    print("\n=== Publish Failed ===")
    print(f"Error: {str(e)}")

    # Example 2: Multiple files with different representations
    print("\n[START] Beginning multi-representation publish process")
    result = publish_to_ayon(
        file_paths=[
            r"C:\Users\alex.szabados\Pictures\download.jpg",
            r"C:\Users\alex.szabados\Pictures\WORKS.png",
        ],
        project_name="alex_playground",
        folder_path="/shots/sh0100",
        product_name="multi_test",
        product_type="render",
        description="Test multi-representation publish",
    )
    print("\n=== Multi-Representation Publish Successful ===")
    print(json.dumps(result, indent=2))

try:
    print("[INIT] Initializing AYON connection")
    ayon_api.init_service(
        server_url=os.getenv("AYON_SERVER_URL"), token=os.getenv("AYON_API_KEY")
    )
    print("\n[START] Beginning sequence publish process")
    result = publish_to_ayon(
        file_paths=[
            r"C:\Users\alex.szabados\Pictures\test.1001.png",
            r"C:\Users\alex.szabados\Pictures\test.1002.png",
            r"C:\Users\alex.szabados\Pictures\test.1003.png",
        ],
        project_name="demo_Big_Episodic",
        folder_path="/sq/sh0100",
        product_name="sequence_test",
        product_type="render",
        description="Test sequence publish",
    )
    print("\n=== Sequence Publish Successful ===")
    print(json.dumps(result, indent=2))
except Exception as e:
    print("\n=== Publish Failed ===")
    print(f"Error: {str(e)}")