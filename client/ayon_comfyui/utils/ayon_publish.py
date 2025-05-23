import os
import json
import shutil
import re
import uuid
from typing import Dict, Any, Optional, List, Tuple, Union

from PIL import Image

import ayon_api


class AyonPublisher:
    """Class for publishing files to AYON with support for sequences and multiple representations."""

    def __init__(self):
        """Initialize the publisher."""
        self.logger = Logger()

    def init_connection(self):
        """Initialize connection to AYON API."""
        self.logger.info("[CONNECTION] Initializing API connection")
        ayon_api.init_service()
        self.logger.info("[CONNECTION] Initialized API connection")

    def publish_to_ayon(
            self,
            file_paths: Union[str, List[str]],
            project_name: str,
            folder_path: str,
            product_name: str,
            product_type: str = "image",
            representation_names: Optional[List[str]] = None,
            description: Optional[str] = None,
    ) -> Dict[str, Any]:
        # TODO add seed to context data
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
        self.logger.info("=== Starting publish process ===")

        # Convert single file path to list for consistent handling
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # Validate files exist
        for file_path in file_paths:
            if not os.path.exists(file_path):
                raise ValueError(f"[ERROR] File does not exist: {file_path}")
        self.logger.info(f"[FILE] Validation passed for {len(file_paths)} files")

        # Initialize connection
        self.init_connection()

        try:
            # Get folder
            folder = self._get_folder(project_name, folder_path)
            folder_id = folder["id"]

            # Get or create product
            product = self._get_or_create_product(
                project_name, folder_id, product_name, product_type
            )
            product_id = product["id"]

            # Get next version
            next_version = self._get_next_version(project_name, product_id)

            # Determine resolution from the first file
            first_file = file_paths[0]
            res_width = None
            res_height = None
            try:
                with Image.open(first_file) as img:
                    res_width, res_height = img.size
            except Exception:
                pass

            # Get project anatomy
            anatomy_data = self._get_project_anatomy(project_name)
            publish_root, template = self._get_template(anatomy_data, product_type)

            # Create version
            version_id = self._create_version(
                project_name,
                product_id,
                next_version,
                description,
                res_width,
                res_height,
            )

            # Detect sequences in the files
            sequences = self._detect_sequence(file_paths)

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

                file_ext = os.path.splitext(files[0])[1].lstrip('.')
                representation_name = os.path.splitext(os.path.basename(files[0]))[0]

                if is_sequence:
                    # Handle sequence publishing
                    result = self._publish_sequence(
                        project_name,
                        folder_path,
                        product_name,
                        product_type,
                        files,
                        representation_name,
                        file_ext,
                        version_id,
                        next_version,
                        template,
                        publish_root,
                    )
                    representation_ids.append(result["representation_id"])
                    publish_paths.extend(result["publish_paths"])
                else:
                    # Handle single file publishing
                    result = self._publish_single_file(
                        project_name,
                        folder_path,
                        product_name,
                        product_type,
                        files[0],
                        representation_name,
                        file_ext,
                        version_id,
                        next_version,
                        template,
                        publish_root,
                    )
                    representation_ids.append(result["representation_id"])
                    publish_paths.append(result["publish_path"])

            return {
                "status": "success",
                "product_id": product_id,
                "version_id": version_id,
                "representation_ids": representation_ids,
                "paths": publish_paths,
                "version": next_version,
            }

        except Exception as e:
            self.logger.error(f"Publish failed: {str(e)}")
            raise

    def publish_image_to_ayon(
            self,
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
        result = self.publish_to_ayon(
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

    def _get_folder(self, project_name: str, folder_path: str) -> Dict[str, Any]:
        """Get folder by path."""
        self.logger.info(f"[FOLDER] Looking for folder: {folder_path}")
        folder = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder:
            raise ValueError(f"[ERROR] Folder not found: {folder_path}")
        self.logger.info(f"[FOLDER] Found folder ID: {folder['id']}")
        return folder

    def _get_or_create_product(
            self, project_name: str, folder_id: str, product_name: str, product_type: str
    ) -> Dict[str, Any]:
        """Get existing product or create new one."""
        self.logger.info(f"[PRODUCT] Looking for product '{product_name}' in folder {folder_id}")
        try:
            product = ayon_api.get_product_by_name(
                project_name=project_name, product_name=product_name, folder_id=folder_id
            )
            if product:
                self.logger.info("[PRODUCT] Found existing product")
                self.logger.debug(json.dumps(product, indent=2))
                return product

            self.logger.info(f"[PRODUCT] Creating new product '{product_name}'")
            product_data = {
                "name": product_name,
                "product_type": product_type.lower(),
                "folder_id": folder_id,
                "data": {"description": "Automatically created product"},
            }
            self.logger.debug(f"[PRODUCT] Creation payload: {json.dumps(product_data, indent=2)}")
            product = ayon_api.create_product(project_name, **product_data)
            self.logger.info("[PRODUCT] Created new product successfully")

            if isinstance(product, str):
                # Server may return only an ID
                try:
                    if hasattr(ayon_api, "get_product"):
                        product = ayon_api.get_product(project_name, product)
                    else:
                        products = ayon_api.get_products(
                            project_name, product_ids=[product]
                        )
                        product = products[0] if products else None
                except Exception:
                    self.logger.warning("Failed to fetch product details; using ID only")
                    product = {"id": product}

            return product
        except Exception as e:
            self.logger.error(f"Product operation failed: {str(e)}")
            raise

    def _get_next_version(self, project_name: str, product_id: str) -> int:
        """Get next version number."""
        self.logger.info(f"[VERSION] Getting versions for product {product_id}")
        try:
            versions = ayon_api.get_versions(project_name, product_ids=[product_id])
            if versions:
                version_numbers = [v["version"] for v in versions]
                next_version = max(version_numbers) + 1
                self.logger.info(f"[VERSION] Found versions: {version_numbers}")
            else:
                next_version = 1
                self.logger.info("[VERSION] No existing versions found")
            self.logger.info(f"[VERSION] Next version will be: {next_version}")
            return next_version
        except Exception as e:
            self.logger.error(f"Version check failed: {str(e)}")
            return 1

    def _get_project_anatomy(self, project_name: str) -> Dict[str, Any]:
        """Get project anatomy data."""
        self.logger.info(f"[ANATOMY] Fetching anatomy for project {project_name}")
        try:
            project = ayon_api.get_project(project_name)
            if not project:
                raise ValueError(f"Project not found: {project_name}")

            anatomy = project.get("config", {})
            if not anatomy:
                raise ValueError("No anatomy data found in project")

            self.logger.info("[ANATOMY] Anatomy data retrieved")
            return anatomy
        except Exception as e:
            self.logger.error(f"Failed to get anatomy data: {str(e)}")
            raise

    def _get_template(self, anatomy_data: Dict[str, Any], product_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Get publish root and template from anatomy data."""
        # Get roots
        roots = anatomy_data.get("roots", {})
        self.logger.debug(f"[PATH] Roots: {roots}")

        publish_root = roots.get("publish", roots.get("default"))
        if not publish_root:
            raise ValueError("No publish root found in anatomy data")
        self.logger.debug(f"[PATH] Publish root: {publish_root}")

        # Get templates
        templates = anatomy_data.get("templates", {}).get("publish", {})
        if not templates:
            raise ValueError("No publish templates found in anatomy data")

        # Find appropriate template
        template = templates.get("ComfyUi")
        if not template:
            raise ValueError(f"No template found for product type {product_type}")

        return publish_root, template

    def _create_version(
            self,
            project_name: str,
            product_id: str,
            version_number: int,
            description: Optional[str] = None,
            resolution_width: Optional[int] = None,
            resolution_height: Optional[int] = None,
    ) -> str:
        """Create a new version."""
        author = (
            os.getenv("AYON_USERNAME")
            or os.getenv("USERNAME")
            or os.getenv("USER")
            or "system"
        )

        version_data = {
            "version": version_number,
            "product_id": product_id,
            "author": author,
            "status": "Pending review",
            "attrib": {},
            "data": {"comment": description or ""},
        }

        if resolution_width is not None and resolution_height is not None:
            version_data["attrib"].update(
                {
                    "resolutionWidth": resolution_width,
                    "resolutionHeight": resolution_height,
                }
            )

        self.logger.debug(f"[VERSION] Creation payload: {json.dumps(version_data, indent=2)}")
        version_id = ayon_api.create_version(project_name, **version_data)
        self.logger.info(f"[VERSION] Created successfully with ID: {version_id}")

        return version_id

    def _detect_sequence(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Detect sequences in a list of file paths.
        Returns a dictionary where:
        - Keys are sequence patterns (or single files if not part of a sequence)
        - Values are lists of files in that sequence
        """
        self.logger.info(f"[SEQUENCE] Analyzing {len(file_paths)} files for sequences")

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

        # Log sequence detection results
        for pattern, files in sequences.items():
            if len(files) > 1:
                self.logger.info(f"[SEQUENCE] Detected sequence '{pattern}' with {len(files)} frames")
            else:
                self.logger.info(f"[SEQUENCE] Single file: {os.path.basename(files[0])}")

        return sequences

    def _extract_frame_info(self, file_path: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract frame number and base name from a file path."""
        filename = os.path.basename(file_path)
        match = re.search(r'(.+?)(\d+)(\.\w+)$', filename)
        if match:
            prefix, frame_num, suffix = match.groups()
            return prefix, int(frame_num)
        return None, None

    def _construct_publish_path(
            self,
            file_path: str,
            project_name: str,
            folder_path: str,
            product_name: str,
            product_type: str,
            representation_name: str,
            version: int,
            template: Dict[str, Any],
            publish_root: Dict[str, Any],
            file_ext: str,
            udim: str = "",
            frame: str = "",
            output: str = "",
    ) -> str:
        """Construct publish path using anatomy templates, handling empty optional fields."""
        self.logger.info("[PATH] Constructing publish path")
        try:
            self.logger.debug(f"[PATH] Using template: {template}")
            directory_template = template.get("directory", "")
            file_template = template.get("file", "")
            self.logger.debug(f"FileTemplate {file_template}")

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
                "ext": file_ext,
                "originalBasename": os.path.splitext(os.path.basename(file_path))[0],
                "output": output,
                "exr": "jpg",
            }

            # Clean up empty optional fields in the filename template
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

            # Remove any double underscores or trailing/leading underscores
            file_template = file_template.replace("__", "_").strip("_")
            self.logger.debug(f"[PATH] Final file template: {file_template}")

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
            self.logger.debug(f"[PATH] Publish directory: {publish_dir}")
            self.logger.debug(f"[PATH] Filename: {filename}")
            self.logger.info(f"[PATH] Full publish path: {publish_path}")

            # Create directory structure
            os.makedirs(publish_dir, exist_ok=True)
            self.logger.info("[PATH] Directory structure created")

            return publish_path
        except Exception as e:
            self.logger.error(f"Failed to construct publish path: {str(e)}")
            raise

    def _create_representation(
            self,
            project_name: str,
            version_id: str,
            representation_name: str,
            files: List[str],
            is_sequence: bool = False,
            original_basename: Optional[str] = None,
            tags: List[str] = None,
            colorspace: str = "sRGB",
            template: str = "",
            resolution_width: Optional[int] = None,
            resolution_height: Optional[int] = None,
    ) -> str:
        """Create a representation with the given files."""
        self.logger.info(f"[REPRESENTATION] Creating representation '{representation_name}'")

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
                "isSequence": is_sequence,
                "context": self._get_context()
            },
            "status": "Pending review",
            "attrib": {
                "path": file_entries[0]["path"],
                "template": "{root[publish]}/{project[name]}/{hierarchy}/{folder[name]}/{product[type]}/{task[name]}/{product[name]}/{task[name]}/v{version:0>3}/{project[code]}_{folder[name]}_{product[name]}_v{version:0>3}<_{output}><.{frame:0>4}>.{ext}"
            }
        }
        rep_data["data"]["context"]["ext"] = os.path.splitext(files[0])[1].lstrip('.')
        rep_data["data"]["context"]["representation"] = os.path.splitext(files[0])[1].lstrip('.')
        if resolution_width is not None and resolution_height is not None:
            rep_data["attrib"].update({
                "resolutionWidth": resolution_width,
                "resolutionHeight": resolution_height,
            })

        self.logger.debug(f"[REPRESENTATION] Creation payload: {json.dumps(rep_data, indent=2)}")
        representation_id = ayon_api.create_representation(project_name, **rep_data)
        self.logger.info(f"[REPRESENTATION] Created successfully with ID: {representation_id}")

        return representation_id

    def _get_context(self) -> Dict[str, Any]:
        """Build representation context from environment variables."""
        ayon_env = {k: v for k, v in os.environ.items() if k.startswith("AYON_")}

        user_name = (
            os.getenv("AYON_USERNAME")
            or os.getenv("USERNAME")
            or os.getenv("USER")
        )

        context = {
            "project": {"name": ayon_env.get("AYON_PROJECT_NAME"), "code": "epi"},
            "folder": {"path": ayon_env.get("AYON_FOLDER_PATH")},
            "task": {"name": ayon_env.get("AYON_TASK_NAME")},
            "user": {"name": user_name} if user_name else {},
        }

        cleaned = {
            k: v
            for k, v in context.items()
            if v and all(vv is not None for vv in v.values())
        }
        return cleaned

    def _publish_sequence(
            self,
            project_name: str,
            folder_path: str,
            product_name: str,
            product_type: str,
            files: List[str],
            representation_name: str,
            file_ext: str,
            version_id: str,
            version_number: int,
            template: Dict[str, Any],
            publish_root: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Publish a sequence of files."""
        # Get frame numbers for sequence
        first_file = files[0]

        res_w = res_h = None
        try:
            with Image.open(first_file) as img:
                res_w, res_h = img.size
        except Exception:
            pass

        prefix, _ = self._extract_frame_info(files[0])
        print(f"@@prefix: {prefix}")
        representation_name = prefix.rstrip(".") if prefix else os.path.splitext(
            os.path.basename(files[0])
        )[0]

        # Create a directory for the sequence
        sequence_publish_paths = []
        for file_path in files:
            _, frame_num = self._extract_frame_info(file_path)
            frame = f"{frame_num:04d}"

            # Construct publish path for each frame
            publish_path = self._construct_publish_path(
                file_path=file_path,
                project_name=project_name,
                folder_path=folder_path,
                product_name=product_name,
                product_type=product_type,
                representation_name=representation_name,
                version=version_number,
                template=template,
                publish_root=publish_root,
                file_ext=file_ext,
                frame=frame,
                output=representation_name,
            )

            # Copy file to publish location
            shutil.copy2(file_path, publish_path)
            self.logger.info(f"[FILE] Published to: {publish_path}")
            sequence_publish_paths.append(publish_path)

        # Create representation for the sequence
        rep_id = self._create_representation(
            project_name=project_name,
            version_id=version_id,
            representation_name=representation_name,
            files=sequence_publish_paths,
            is_sequence=True,
            original_basename=representation_name,
            tags=["review", "sequence"],
            template=template,
            resolution_width=res_w,
            resolution_height=res_h,
        )

        # Upload first frame as reviewable
        review_data = {
            "version_id": version_id,
            "filepath": sequence_publish_paths[0],
        }
        ayon_api.upload_reviewable(project_name, **review_data)

        return {
            "representation_id": rep_id,
            "publish_paths": sequence_publish_paths
        }

    def _publish_single_file(
            self,
            project_name: str,
            folder_path: str,
            product_name: str,
            product_type: str,
            file_path: str,
            representation_name: str,
            file_ext: str,
            version_id: str,
            version_number: int,
            template: Dict[str, Any],
            publish_root: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Publish a single file."""
        res_w = res_h = None
        try:
            with Image.open(file_path) as img:
                res_w, res_h = img.size
        except Exception:
            pass

        # Construct publish path
        publish_path = self._construct_publish_path(
            file_path=file_path,
            project_name=project_name,
            folder_path=folder_path,
            product_name=product_name,
            product_type=product_type,
            representation_name=representation_name,
            version=version_number,
            template=template,
            publish_root=publish_root,
            file_ext=file_ext,
            output=representation_name,
        )

        # Copy file to publish location
        shutil.copy2(file_path, publish_path)
        self.logger.info(f"[FILE] Published to: {publish_path}")

        # Create representation
        rep_id = self._create_representation(
            project_name=project_name,
            version_id=version_id,
            representation_name=representation_name,
            files=[publish_path],
            is_sequence=False,
            template=template,
            original_basename=os.path.splitext(os.path.basename(file_path))[0],
            resolution_width=res_w,
            resolution_height=res_h,
        )

        # Upload reviewable
        review_data = {
            "version_id": version_id,
            "filepath": publish_path,
        }
        ayon_api.upload_reviewable(project_name, **review_data)

        return {
            "representation_id": rep_id,
            "publish_path": publish_path
        }


class Logger:
    """Simple logger class for consistent logging."""

    def __init__(self, debug_mode: bool = False):
        """Initialize logger with optional debug mode."""
        self.debug_mode = debug_mode

    def info(self, message: str):
        """Log info level message."""
        print(message)

    def error(self, message: str):
        """Log error level message."""
        print(f"\n[ERROR] {message}")

    def debug(self, message: str):
        """Log debug level message if debug mode is enabled."""
        if self.debug_mode:
            print(f"[DEBUG] {message}")

    def debug_print_response(self, response, context: str = ""):
        """Print detailed response information for debugging."""
        if not self.debug_mode:
            return

        print(f"\n[DEBUG] {context} Response:")
        print(f"Status Code: {response.status_code}")
        print("Headers:")
        for k, v in response.headers.items():
            print(f"  {k}: {v}")
        print("Body:")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)


def run_examples():
    """Run example publish operations."""
    publisher = AyonPublisher()

    try:
        print("[INIT] Initializing AYON connection")
        ayon_api.init_service(
            server_url=os.getenv("AYON_SERVER_URL"),
            token=os.getenv("AYON_API_KEY")
        )

        # Example 1: Single file publish (legacy method)
        print("\n[START] Beginning single file publish process")
        result = publisher.publish_image_to_ayon(
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

    try:
        # Example 2: Multiple files with different representations
        print("\n[START] Beginning multi-representation publish process")
        result = publisher.publish_to_ayon(
            file_paths=[
                r"C:\Users\alex.szabados\Pictures\download.jpg",
                r"C:\Users\alex.szabados\Pictures\WORKS.png",
            ],
            project_name="demo_Big_Episodic",
            folder_path="/sq/sh0100",
            product_name="multi_test",
            product_type="render",
            description="Test multi-representation publish",
        )
        print("\n=== Multi-Representation Publish Successful ===")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print("\n=== Publish Failed ===")
        print(f"Error: {str(e)}")

    try:
        # Example 3: Sequence publish
        print("\n[START] Beginning sequence publish process")
        result = publisher.publish_to_ayon(
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


if __name__ == "__main__":
    run_examples()
