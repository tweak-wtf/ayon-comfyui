import os
import git
import yaml
import shutil
import socket
import ayon_api
import subprocess
from pathlib import Path
from qtpy import QtWidgets, QtCore

from ayon_applications import (
    PreLaunchHook,
    LaunchTypes,
)
from ayon_core.lib import Logger, StringTemplate
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.template_data import get_template_data


from ayon_comfyui import ADDON_ROOT, ADDON_NAME, ADDON_VERSION


log = Logger.get_logger(__name__)


class SpinnerDialog(QtWidgets.QDialog):
    def __init__(self, message="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Please wait")
        self.setModal(True)
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel(message)
        self.spinner = QtWidgets.QProgressBar(self)
        self.spinner.setRange(0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.spinner)
        self.setLayout(layout)
        self.setFixedSize(300, 80)

    def set_message(self, message):
        self.label.setText(message)
        QtWidgets.QApplication.processEvents()

class Worker(QtCore.QThread):
    finished = QtCore.Signal()
    progress = QtCore.Signal(str)

    def __init__(self, func):
        super().__init__()
        self.func = func

    def run(self):
        self.func(progress_callback=self.progress.emit)
        self.finished.emit()

def run_with_spinner(func, msg=""):
    spinner = SpinnerDialog(msg)
    worker = Worker(func)

    aborted = False
    def abort():
        nonlocal aborted
        aborted = True
        worker.terminate()
        worker.wait()

    worker.finished.connect(spinner.accept)
    worker.progress.connect(spinner.set_message)
    spinner.rejected.connect(abort)

    worker.start()
    spinner.exec_()
    worker.wait()
    return not aborted

class ComfyUIPreLaunchHook(PreLaunchHook):
    """Inject cli arguments to shell point at launch script."""

    hosts = {"comfyui"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        if self.server_is_running:
            raise RuntimeError(
                "ComfyUI server is already running. "
                "Please stop it before launching again."
            )

        if not run_with_spinner(self.pre_launch_setup):
            raise RuntimeError("Pre-launch setup was aborted by user.")
        self.run_server()

    @property
    def server_is_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            try:
                sock.connect(("127.0.0.1", 8188))   # hardcoded until making it dynamic via server settings
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                return False

    def pre_launch_setup(self, progress_callback=None):
        self.pre_process(progress_callback)
        self.cleanup_orphaned_plugins(progress_callback)
        
        # Add a small delay to ensure filesystem operations are complete
        import time
        time.sleep(0.5)
        
        self.clone_repositories(progress_callback)
        self.configure_extra_models(progress_callback)
        self.configure_custom_nodes()

    def pre_process(self, progress_callback=None):
        progress_callback("Pre-processing...")
        anatomy = Anatomy(project_name=self.data["project_name"])
        self.tmpl_data = get_template_data(self.data["project_entity"])
        self.tmpl_data.update({"root": anatomy.roots})

        self.addon_settings = ayon_api.get_addon_project_settings(
            ADDON_NAME, ADDON_VERSION, self.tmpl_data["project"]["name"]
        )

        comfy_root_tmpl = StringTemplate(
            self.addon_settings["repositories"]["base_template"]
        )
        self.comfy_root = Path(comfy_root_tmpl.format_strict(self.tmpl_data))
        log.debug(f"{self.comfy_root = }")

        self.plugins = self.addon_settings["repositories"]["plugins"]
        # i found these deps to be the bare minimum to import ayon_core
        self.extra_dependencies = {"platformdirs", "semver", "clique", "ayon-python-api"}
        for plugin in self.plugins:
            if plugin.get("extra_dependencies"):
                self.extra_dependencies.update(plugin["extra_dependencies"])

        # resolve extra flags templates
        self.extra_flags = []
        for flag in self.addon_settings.get("extra_flags", []):
            tmpl = StringTemplate(flag)
            resolved_flag = tmpl.format_strict(self.tmpl_data)
            self.extra_flags.append(resolved_flag)

        self.cache_dir = None
        if self.addon_settings["caching"].get("enabled"):
            cache_tmpl = self.addon_settings["caching"]["cache_dir_template"]
            self.cache_dir = StringTemplate(cache_tmpl).format_strict(self.tmpl_data)

        # get installed CUDA version and build correct pypi index url
        try:
            smi_version_details = subprocess.check_output(
                ["nvidia-smi", "--version"], text=True
            ).strip()
        except subprocess.CalledProcessError as e:
            log.error(f"Failed to execute `nvidia-smi`: {e} Please ensure NVIDIA drivers are installed.")
        
        cuda_version = None
        for line in smi_version_details.splitlines():
            if "CUDA Version" in line:
                parts = line.split(":")
                cuda_version = parts[1].strip()
                break
        if not cuda_version:
            log.error("Could not determine CUDA version from `nvidia-smi` output.")
            raise RuntimeError("CUDA version could not be determined.")

        pypi_url_map = {
            "11.8": {
                "stable": "https://download.pytorch.org/whl/cu118",
                "nightly": None,
            },
            "12.6": {
                "stable": "https://download.pytorch.org/whl/cu126",
                "nightly": "https://download.pytorch.org/whl/nightly/cu126",
            },
            "12.8": {
                "stable": "https://download.pytorch.org/whl/cu128",
                "nightly": "https://download.pytorch.org/whl/nightly/cu128",
            },
            "12.9": {
                "stable": None,
                "nightly": "https://download.pytorch.org/whl/nightly/cu129",
            },
        }
        if bool(self.addon_settings["venv"]["use_torch_nightly"]):
            self.pypi_url = pypi_url_map[cuda_version]["nightly"]
        else:
            self.pypi_url = pypi_url_map[cuda_version]["stable"]

        self.py_version = self.addon_settings["venv"]["python_version"]

    def clone_repositories(self, progress_callback=None):
        def git_clone(url: str, dest: Path, tag: str = "") -> git.Repo:
            if not dest.exists():
                log.info(f"Cloning {url} to {dest}")
                repo = git.Repo.clone_from(url, dest)
            else:
                repo = git.Repo(dest)

            repo.git.fetch(tags=True)
            if repo.is_dirty(untracked_files=True):
                self.log.info(f"Stashing uncommitted changes in {repo}")
                repo.git.stash("save", "--include-untracked")

            if tag:
                log.info(f"Checking out tag {tag} for {repo}")
                repo.git.checkout(tag)
            else:
                repo.remotes.origin.pull()
            return repo

        app = self.launch_context.data["app"]
        base_url = self.addon_settings["repositories"]["base_url"]
        git_clone(
            url=base_url,
            dest=self.comfy_root,
            tag=app.name,
        )

        # clone custom nodes
        for plugin in self.plugins:
            plugin_name = Path(plugin["url"]).stem
            progress_callback(f"Setting up Plugin: {plugin_name}")
            plugin_root = self.comfy_root / "custom_nodes" / plugin_name
            plugin.update({"root": plugin_root})
            git_clone(
                url=plugin["url"],
                dest=plugin_root,
                tag=plugin["tag"],
            )

            if plugin_name.lower() == "comfyui-manager":
                self.log.info("Configuring comfyui-manager...")
                self.log.info(plugin_name)
                self.log.info(plugin_root)
                # use uv instead of pip to install comfyui-manager
                config = plugin_root / "config.ini"
                self.log.info(f"Configuring comfyui-manager at {config}")
                with open(config, "w+") as writer:
                    writer.write(
                        "[default]\nuse_uv = true\n"
                    )

    def cleanup_orphaned_plugins(self, progress_callback=None):
        """Remove plugins from custom_nodes folder that are no longer in Ayon settings."""
        progress_callback("Cleaning up orphaned plugins...")
        
        custom_nodes_dir = self.comfy_root / "custom_nodes"
        if not custom_nodes_dir.exists():
            log.info("Custom nodes directory does not exist, skipping cleanup.")
            return
        
        # Get list of plugins from Ayon settings
        ayon_plugin_names = set()
        for plugin in self.plugins:
            plugin_name = Path(plugin["url"]).stem
            ayon_plugin_names.add(plugin_name)
        
        # Files that should never be removed
        protected_files = {"example_node.py.example", "websocket_image_save.py"}
        
        # Scan custom_nodes directory for orphaned plugins
        for item in custom_nodes_dir.iterdir():
            if not item.is_dir():
                continue
                
            plugin_name = item.name
            
            # Skip if this is a protected file (though it shouldn't be a directory)
            if plugin_name in protected_files:
                log.info(f"Skipping protected file: {plugin_name}")
                continue
            
            # Skip if this plugin is still in Ayon settings
            if plugin_name in ayon_plugin_names:
                log.debug(f"Plugin {plugin_name} is still in Ayon settings, keeping it.")
                continue
            
            # This plugin is orphaned, remove it
            log.info(f"Removing orphaned plugin: {plugin_name}")
            progress_callback(f"Removing orphaned plugin: {plugin_name}")
            
            try:
                # Check if this is a Git repository and handle it properly
                if (item / ".git").exists():
                    log.info(f"Detected Git repository for {plugin_name}, using Git cleanup")
                    self._remove_git_repository(item, plugin_name, progress_callback)
                else:
                    # Use a more robust deletion method for non-Git directories
                    self._remove_directory_robust(item, plugin_name, progress_callback)
                    
            except Exception as e:
                log.error(f"Failed to remove orphaned plugin {plugin_name}: {e}")
                progress_callback(f"Failed to remove {plugin_name}: {e}")

    def _remove_git_repository(self, repo_path, plugin_name, progress_callback=None):
        """Remove a Git repository safely by first cleaning up Git objects."""
        try:
            # Try to use Git to clean up the repository first
            repo = git.Repo(repo_path)
            
            # Remove any locks that might exist
            git_dir = repo_path / ".git"
            for lock_file in git_dir.glob("*.lock"):
                try:
                    lock_file.unlink()
                except Exception as e:
                    log.warning(f"Could not remove lock file {lock_file}: {e}")
            
            # Close the repository to release any file handles
            repo.close()
            
        except Exception as e:
            log.warning(f"Could not clean up Git repository {plugin_name}: {e}")
        
        # Now try to remove the directory with robust deletion
        self._remove_directory_robust(repo_path, plugin_name, progress_callback)

    def _remove_directory_robust(self, dir_path, plugin_name, progress_callback=None):
        """Remove a directory using a more robust method that handles read-only files."""
        import stat
        
        def on_rm_error(func, path, exc_info):
            """Error handler for shutil.rmtree that makes files writable and retries."""
            # Make the file writable and try again
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:
                log.warning(f"Could not make {path} writable: {e}")
                # If we still can't delete it, just log and continue
                log.warning(f"Could not remove {path}, skipping...")
        
        try:
            # Use shutil.rmtree with error handler
            shutil.rmtree(dir_path, onerror=on_rm_error)
            log.info(f"Successfully removed orphaned plugin: {plugin_name}")
        except Exception as e:
            log.error(f"Failed to remove directory {plugin_name} even with robust method: {e}")
            progress_callback(f"Failed to remove {plugin_name}: {e}")
            raise

    def configure_extra_models(self, progress_callback=None):
        progress_callback("Configuring extra models...")
        enabled = self.addon_settings["extra_models"].get("enabled")
        if not enabled:
            log.info("Extra models are not enabled.")
            return
        extra_models_dir_tmpl = StringTemplate(
            self.addon_settings["extra_models"]["dir_template"]
        )
        extra_models_dir = Path(extra_models_dir_tmpl.format_strict(self.tmpl_data))
        extra_model_dirs = {
            folder for folder in extra_models_dir.iterdir() if folder.is_dir()
        }
        if not extra_model_dirs:
            log.info(f"No extra models found in {extra_models_dir}.")
            return

        extra_models_map: dict[str, str] = {}
        for model_dir in extra_model_dirs:
            model_key = model_dir.name
            extra_models_map[model_key] = model_dir.as_posix()

        if self.addon_settings["extra_models"].get("copy_to_base"):
            self.__copy_extra_models(extra_models_map, progress_callback)
        else:
            self.__reference_extra_models(extra_models_map, progress_callback)

    def __copy_extra_models(self, extra_models_map: dict[str, Path], progress_callback=None):
        for model_key, model_dir in extra_models_map.items():
            model_dest = self.comfy_root / "models" / model_key
            if not model_dest.exists():
                msg = f"Copying {model_key} from {model_dir} to {model_dest}"
                log.info(msg)
                progress_callback(msg)
                shutil.copytree(model_dir, model_dest)
            else:
                log.info(f"Model {model_key} already exists at {model_dest}")

    def __reference_extra_models(self, extra_models_map: dict[str, Path], progress_callback=None):
        progress_callback("Referencing extra models in local config...")
        # TODO: refactor writing to config for configure_custom_nodes
        # get or create config file
        config_file = self.comfy_root / "extra_model_paths.yaml"
        if not config_file.exists():
            example_config = self.comfy_root / "extra_model_paths.yaml.example"
            shutil.copyfile(example_config, config_file)

        # read current settings
        with config_file.open("r") as config_reader:
            config = yaml.safe_load(config_reader)
            log.info(f"Current config: {config}")

        # update config
        new_conf = config.copy() if config else {}
        new_conf.update({"comfyui": extra_models_map})
        with config_file.open("w+") as config_writer:
            yaml.safe_dump(new_conf, config_writer)

    def configure_custom_nodes(self):
        custom_nodes_dir = ADDON_ROOT / "custom_nodes"
        config_file = self.comfy_root / "extra_model_paths.yaml"
        if not config_file.exists():
            example_config = ADDON_ROOT / "extra_model_paths.yaml.example"
            shutil.copyfile(example_config, config_file)

        # read current settings
        with config_file.open("r") as config_reader:
            config = yaml.safe_load(config_reader)
            log.info(f"Current config: {config}")

        # update config
        new_conf = config.copy() if config else {}
        new_conf.update(
            {
                "other_ui": {
                    "custom_nodes": custom_nodes_dir.as_posix()
                }
            }
        )
        with config_file.open("w+") as config_writer:
            yaml.safe_dump(new_conf, config_writer)

    def run_server(self):
        launch_script = ADDON_ROOT / "tools" / "install_and_run_server_venv.ps1"

        _cmd: list = [launch_script.as_posix()]

        launch_args = []
        if self.plugins:
            launch_args.append("-plugins")
            plugin_names = [plugin["root"].name for plugin in self.plugins]
            launch_args.append(",".join(plugin_names))
        if self.extra_dependencies:
            launch_args.append("-extraDependencies")
            launch_args.append(",".join(self.extra_dependencies))
        if self.cache_dir:
            launch_args.append("-cacheDir")
            launch_args.append(self.cache_dir)
        if self.extra_flags:
            launch_args.append("-extraFlags")
            launch_args.append(",".join(self.extra_flags))
        if self.pypi_url:
            launch_args.append("-pypiUrl")
            launch_args.append(self.pypi_url)
        if self.py_version:
            launch_args.append("-pythonVersion")
            launch_args.append(self.py_version)

        _cmd.extend(launch_args)
        cmd = " ".join([str(arg) for arg in _cmd])
        launch_args = [
            "powershell.exe",
            "-Command",
            f"Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', '{cmd}'",
        ]
        log.info(f"{cmd = }")
        env = self.data["env"].copy()
        # $PYTHONPATH: only passthrough ayon_core addon path and nothing else
        # needed for comfyui to import the ayon_core module, well at least lib.StringTemplate
        paths = [
            ppath
            for ppath in env["PYTHONPATH"].split(os.pathsep)
            if "core" in ppath and "ayon_core" not in ppath
        ]
        # Add the addon parent directory so the `ayon_comfyui` package can be
        # discovered when ComfyUI loads custom nodes. Using the addon root
        # directly (which points inside the package) prevents Python from
        # locating the package itself.
        paths.append(str(ADDON_ROOT.parent))
        env["PYTHONPATH"] = os.pathsep.join(paths)

        popen_kwargs = {
            "stdout": None,
            "stderr": None,
            "cwd": self.comfy_root,
            "env": env,
            "creationflags": subprocess.CREATE_NEW_CONSOLE,
        }

        self.launch_context.launch_args = launch_args
        self.launch_context.kwargs = popen_kwargs
