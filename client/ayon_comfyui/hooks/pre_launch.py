import git
import sys
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
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    spinner = SpinnerDialog(msg)
    worker = Worker(func)

    aborted = False
    def abort():
        nonlocal aborted
        aborted = True
        worker.terminate()
        worker.wait()
        app.quit()

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
        self.clone_repositories(progress_callback)
        self.configure_extra_models(progress_callback)

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
        self.extra_dependencies = set()
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
                "stable": "https://download.pytorch.org/whl/cu129",
                "nightly": "https://download.pytorch.org/whl/nightly/cu129",
            },
        }
        if bool(self.addon_settings["venv"]["use_torch_nightly"]):
            self.pypi_url = pypi_url_map[cuda_version]["nightly"]
        else:
            self.pypi_url = pypi_url_map[cuda_version]["stable"]

        self.py_version = self.addon_settings["venv"]["python_version"]
        self.uv_path = self.addon_settings["venv"]["uv_path"]

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

    def configure_extra_models(self, progress_callback=None):
        progress_callback("Configuring extra models...")
        extra_models_dir_tmpl = StringTemplate(
            self.addon_settings["extra_models"]["dir_template"]
        )
        extra_models_dir = Path(extra_models_dir_tmpl.format_strict(self.tmpl_data))
        extra_model_dirs = {
            folder for folder in extra_models_dir.iterdir() if folder.is_dir()
        }
        if not extra_model_dirs:
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

    def run_server(self):
        launch_script = ADDON_ROOT / "tools" / "install_and_run_server_venv.ps1"

        _cmd: list = [launch_script.as_posix()]

        launch_args = []
        if self.uv_path:
            launch_args.append("-uvPath")
            launch_args.append(self.uv_path)
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
            f"Start-Process powershell.exe -ArgumentList '-NoExit', '-NoProfile', '-Command', '{cmd}'",
        ]
        log.info(f"{cmd = }")
        env = self.data["env"].copy()
        if "PYTHONPATH" in env:
            del env["PYTHONPATH"]

        popen_kwargs = {
            "stdout": None,
            "stderr": None,
            "cwd": self.comfy_root,
            "env": env,
            "creationflags": subprocess.CREATE_NEW_CONSOLE,
        }

        self.launch_context.launch_args = launch_args
        self.launch_context.kwargs = popen_kwargs
