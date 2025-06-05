import os
import json
import shutil
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union
import hashlib

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

    def _calculate_file_hash(self, filepath, *args):
        """Generate simple identifier for a source file.
        This is used to identify whether a source file has previously been
        processe into the pipeline, e.g. a texture.
        The hash is based on source filepath, modification time and file size.
        This is only used to identify whether a specific source file was already
        published before from the same location with the same modification date.
        We opt to do it this way as opposed to Avalanch C4 hash as this is much
        faster and predictable enough for all our production use cases.
        Args:
            filepath (str): The source file path.
        You can specify additional arguments in the function
        to allow for specific 'processing' values to be included.
        """
        # We replace dots with comma because . cannot be a key in a pymongo dict.
        file_name = os.path.basename(filepath)
        time = str(os.path.getmtime(filepath))
        size = str(os.path.getsize(filepath))
        return "|".join([file_name, time, size] + list(args)).replace(".", ",")

    def publish_to_ayon(
            self,
            file_paths: Union[str, List[str]],
            project_name: str,
            folder_path: str,
            product_name: str,
            product_type: str = "image",
            task_name: str = "",
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
            task_name: Name of the task for context information
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
            folder_type = folder.get("type") or folder.get("folderType")

            # Get or create product
            product = self._get_or_create_product(
                project_name, folder_id, product_name, product_type
            )
            product_id = product["id"]

            # Get next version
            next_version = self._get_next_version(project_name, product_id)

            # Detect sequences in the files
            sequences = self._detect_sequence(file_paths)

            frame_start = frame_end = None
            for seq_files in sequences.values():
                _, start = self._extract_frame_info(seq_files[0])
                _, end = self._extract_frame_info(seq_files[-1])
                if start is not None:
                    frame_start = start if frame_start is None else min(frame_start, start)
                if end is not None:
                    frame_end = end if frame_end is None else max(frame_end, end)

            if frame_start is None:
                frame_start = 1
            if frame_end is None:
                frame_end = frame_start

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
            roots = anatomy_data.get("roots", {})

            # Create version
            version_id = self._create_version(
                project_name,
                product_id,
                next_version,
                description,
                res_width,
                res_height,
                frame_start,
                frame_end,
            )

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
                        folder_type,
                        product_name,
                        product_type,
                        task_name,
                        files,
                        representation_name,
                        file_ext,
                        version_id,
                        next_version,
                        template,
                        publish_root,
                        roots,
                    )
                    representation_ids.append(result["representation_id"])
                    publish_paths.extend(result["publish_paths"])
                else:
                    # Handle single file publishing
                    result = self._publish_single_file(
                        project_name,
                        folder_path,
                        folder_type,
                        product_name,
                        product_type,
                        task_name,
                        files[0],
                        representation_name,
                        file_ext,
                        version_id,
                        next_version,
                        template,
                        publish_root,
                        roots,
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
                        products = list(
                            ayon_api.get_products(
                                project_name, product_ids=[product]
                            )
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
            # ``ayon_api.get_versions`` can return a generator. Convert it to a
            # list so that truthiness checks behave as expected and the content
            # can be reused multiple times.
            versions = list(
                ayon_api.get_versions(project_name, product_ids=[product_id])
            )

            if versions:
                version_numbers = [v.get("version") for v in versions if "version" in v]
                if version_numbers:
                    next_version = max(version_numbers) + 1
                else:
                    next_version = 1
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
            frame_start: Optional[int] = None,
            frame_end: Optional[int] = None,
            fps: float = 25.0,
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
            "attrib": {
                "fps": fps,
                "clipIn": 1,
                "clipOut": 1,
                "pixelAspect": 1.0,
                "handleStart": 0,
                "handleEnd": 0,
            },
            "data": {
                "comment": description or "",
                "colorspace": "scene_linear",
                "step": 1,
                "time": datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
            },
        }

        if frame_start is not None:
            version_data["attrib"]["frameStart"] = frame_start
        if frame_end is not None:
            version_data["attrib"]["frameEnd"] = frame_end

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
            task_name: str = "",
    ) -> Tuple[str, str]:
        """Construct publish path using anatomy templates.

        Returns the publish path and the template string used. The ``task_name``
        parameter is injected into template data.
        """
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

            project_entity = ayon_api.get_project(project_name, fields=["code"])
            project_code = project_entity["code"]
            template_data = {
                "root": {"publish": publish_root.get("windows")},
                "project": {
                    "name": project_name,
                    "code": project_code,
                },
                "folder": {"name": folder_name, "path": folder_path},
                "hierarchy": hierarchy,
                "task": {"name": task_name},
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

            # Prepare two versions of the filename template:
            # one with placeholders preserved for the template string and one
            # with concrete values filled in for the actual publish path.
            template_file_template = file_template
            publish_file_template = file_template

            # Handle optional UDIM value
            if not udim:
                template_file_template = template_file_template.replace("<_{udim}>", "")
                publish_file_template = publish_file_template.replace("<_{udim}>", "")
            else:
                template_file_template = template_file_template.replace("<_{udim}>", "_{udim}")
                publish_file_template = publish_file_template.replace("<_{udim}>", f"_{udim}")

            # Handle optional frame value
            if not frame:
                template_file_template = template_file_template.replace("<.{frame}>", "")
                publish_file_template = publish_file_template.replace("<.{frame}>", "")
            else:
                template_file_template = template_file_template.replace("<.{frame}>", ".{frame}")
                publish_file_template = publish_file_template.replace("<.{frame}>", f".{frame}")

            # Handle optional output value
            if not output:
                template_file_template = template_file_template.replace("<_{output}>", "")
                publish_file_template = publish_file_template.replace("<_{output}>", "")
            else:
                template_file_template = template_file_template.replace("<_{output}>", "_{output}")
                publish_file_template = publish_file_template.replace("<_{output}>", f"_{output}")

            # Remove any double underscores or trailing/leading underscores
            template_file_template = template_file_template.replace("__", "_").strip("_")
            publish_file_template = publish_file_template.replace("__", "_").strip("_")
            self.logger.debug(f"[PATH] Final file template: {publish_file_template}")

            # Format paths
            publish_dir = directory_template.format(**template_data)
            filename = publish_file_template.format(**template_data)

            # Clean up the filename (remove double underscores and empty sections)
            filename = filename.replace("__", "_").strip("_")

            # Ensure we don't have double extensions
            if filename.endswith(f".{representation_name}.{representation_name}"):
                filename = filename.replace(
                    f".{representation_name}.{representation_name}",
                    f".{representation_name}",
                )

            publish_path = os.path.normpath(os.path.join(publish_dir, filename))
            template_str = os.path.normpath(os.path.join(directory_template, template_file_template))
            self.logger.debug(f"[PATH] Publish directory: {publish_dir}")
            self.logger.debug(f"[PATH] Filename: {filename}")
            self.logger.info(f"[PATH] Full publish path: {publish_path}")

            # Create directory structure
            os.makedirs(publish_dir, exist_ok=True)
            self.logger.info("[PATH] Directory structure created")

            return publish_path, template_str
        except Exception as e:
            self.logger.error(f"Failed to construct publish path: {str(e)}")
            raise

    def _create_representation(
            self,
            project_name: str,
            version_id: str,
            representation_name: str,
            files: List[str],
            folder_path: str,
            folder_type: Optional[str],
            product_name: str,
            product_type: str,
            version_number: int,
            publish_root: Dict[str, Any],
            root_paths: Dict[str, Any],
            task_name: str = "",
            is_sequence: bool = False,
            original_basename: Optional[str] = None,
            tags: List[str] = None,
            colorspace: str = "sRGB",
            template: str = "",
            resolution_width: Optional[int] = None,
            resolution_height: Optional[int] = None,
            frame_start: Optional[int] = None,
            frame_end: Optional[int] = None,
            frame_placeholder: Optional[str] = None,
    ) -> str:
        """Create a representation with the given files.

        The ``template`` argument should be the formatted anatomy template used
        when constructing the publish path. ``task_name`` will be injected into
        the context information.
        """
        self.logger.info(f"[REPRESENTATION] Creating representation '{representation_name}'")

        file_entries = []
        for file_path in files:
            file_entries.append({
                "id": uuid.uuid1().hex,
                "name": os.path.basename(file_path),
                "path": file_path,
                "size": os.path.getsize(file_path),
                "hash": self._calculate_file_hash(file_path),
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
                "context": self._get_context(
                    project_name,
                    folder_path,
                    folder_type,
                    product_name,
                    product_type,
                    representation_name,
                    version_number,
                    root_paths,
                    task_name,
                ),
            },
            "status": "Pending review",
            "attrib": {
                "path": file_entries[0]["path"],
                "template": template,
            }
        }
        context_data = rep_data["data"]["context"]
        if is_sequence:
            if frame_placeholder is None:
                frame_placeholder = "####"
            context_data["frame"] = frame_placeholder
            if frame_start is not None:
                context_data["frameStart"] = frame_start
            if frame_end is not None:
                context_data["frameEnd"] = frame_end
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

    def _get_context(
            self,
            project_name: str,
            folder_path: str,
            folder_type: Optional[str],
            product_name: str,
            product_type: str,
            representation_name: str,
            version_number: int,
            root_paths: Dict[str, Any],
            task_name: str = "",
    ) -> Dict[str, Any]:
        """Build representation context from parameters and environment.

        The ``task_name`` argument overrides ``AYON_TASK_NAME`` if provided.
        """
        ayon_env = {k: v for k, v in os.environ.items() if k.startswith("AYON_")}

        user_name = (
            os.getenv("AYON_USERNAME")
            or os.getenv("USERNAME")
            or os.getenv("USER")
        )

        folder_parts = folder_path.strip("/").split("/") if folder_path else []
        asset_name = folder_parts[-1] if folder_parts else ""
        hierarchy = "/".join(folder_parts[:-1]) if len(folder_parts) > 1 else ""
        project_entity = ayon_api.get_project(project_name, fields=["code"])
        project_code = project_entity["code"]

        context = {
            "asset": asset_name,
            "subset": product_name,
            "hierarchy": hierarchy,
            "family": product_type,
            "project": {
                "name": project_name,
                #"code": ayon_env.get("AYON_PROJECT_CODE", project_name[:3]),
                "code": project_code,
            },
            "folder": {
                "path": folder_path,
                "name": asset_name,
                "parents": folder_parts[:-1],
                "type": folder_type,
            },
            "product": {"name": product_name, "type": product_type},
            "representation": representation_name,
            "task": {
                "name": task_name or ayon_env.get("AYON_TASK_NAME"),
                "type": ayon_env.get("AYON_TASK_TYPE"),
                "short": ayon_env.get("AYON_TASK_SHORT"),
            },
            "user": user_name,
            "username": user_name,
            "version": version_number,
            "root": root_paths,
        }

        cleaned = {k: v for k, v in context.items() if v not in (None, "", {})}
        return cleaned

    def _publish_sequence(
            self,
            project_name: str,
            folder_path: str,
            folder_type: Optional[str],
            product_name: str,
            product_type: str,
            task_name: str,
            files: List[str],
            representation_name: str,
            file_ext: str,
            version_id: str,
            version_number: int,
            template: Dict[str, Any],
            publish_root: Dict[str, Any],
            root_paths: Dict[str, Any]
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

        prefix, first_frame_num = self._extract_frame_info(files[0])
        _, last_frame_num = self._extract_frame_info(files[-1])
        representation_name = prefix.rstrip(".") if prefix else os.path.splitext(
            os.path.basename(files[0])
        )[0]
        frame_placeholder = "####"

        # Create a directory for the sequence
        sequence_publish_paths = []
        sequence_template = ""
        for file_path in files:
            _, frame_num = self._extract_frame_info(file_path)
            frame = f"{frame_num:04d}"

            # Construct publish path for each frame
            publish_path, frame_template = self._construct_publish_path(
                file_path=file_path,
                project_name=project_name,
                folder_path=folder_path,
                task_name=task_name,
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

            if not sequence_template:
                sequence_template = frame_template

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
            folder_path=folder_path,
            folder_type=folder_type,
            product_name=product_name,
            product_type=product_type,
            version_number=version_number,
            publish_root=publish_root,
            root_paths=root_paths,
            task_name=task_name,
            is_sequence=True,
            original_basename=representation_name,
            tags=["review", "sequence"],
            template=sequence_template,
            resolution_width=res_w,
            resolution_height=res_h,
            frame_start=first_frame_num,
            frame_end=last_frame_num,
            frame_placeholder=frame_placeholder,
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
            folder_type: Optional[str],
            product_name: str,
            product_type: str,
            task_name: str,
            file_path: str,
            representation_name: str,
            file_ext: str,
            version_id: str,
            version_number: int,
            template: Dict[str, Any],
            publish_root: Dict[str, Any],
            root_paths: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Publish a single file with optional ``task_name`` for context."""
        res_w = res_h = None
        try:
            with Image.open(file_path) as img:
                res_w, res_h = img.size
        except Exception:
            pass

        # Construct publish path
        publish_path, rep_template = self._construct_publish_path(
                file_path=file_path,
                project_name=project_name,
                folder_path=folder_path,
                task_name=task_name,
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
            folder_path=folder_path,
            folder_type=folder_type,
            product_name=product_name,
            product_type=product_type,
            version_number=version_number,
            publish_root=publish_root,
            root_paths=root_paths,
            task_name=task_name,
            is_sequence=False,
            template=rep_template,
            original_basename=os.path.splitext(os.path.basename(file_path))[0],
            resolution_width=res_w,
            resolution_height=res_h,
            frame_start=None,
            frame_end=None,
            frame_placeholder=None,
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

    def warning(self, message: str):
        """Log warning level message."""
        print(f"[WARNING] {message}")

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
