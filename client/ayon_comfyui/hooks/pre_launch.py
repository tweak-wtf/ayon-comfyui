import git
import yaml
import shutil
import ayon_api
import subprocess
from pathlib import Path

from ayon_applications import (
    PreLaunchHook,
    LaunchTypes,
)
from ayon_core.lib import Logger, StringTemplate
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.template_data import get_template_data


from ayon_comfyui import ADDON_ROOT, ADDON_NAME, ADDON_VERSION


log = Logger.get_logger(__name__)


class ComfyUIPreLaunchHook(PreLaunchHook):
    """Inject cli arguments to shell point at launch script."""

    hosts = {"comfyui"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        self.pre_process()
        self.clone_repositories()
        self.configure_extra_models()
        self.run_server()

    def pre_process(self):
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

        self.cache_dir = None
        if self.addon_settings["caching"].get("enabled"):
            cache_tmpl = self.addon_settings["caching"]["cache_dir_template"]
            self.cache_dir = StringTemplate(cache_tmpl).format_strict(self.tmpl_data)

    def clone_repositories(self):
        def git_clone(url: str, dest: Path, tag: str = "") -> git.Repo:
            if not dest.exists():
                log.info(f"Cloning {url} to {dest}")
                repo = git.Repo.clone_from(url, dest)
            else:
                repo = git.Repo(dest)

            repo.git.fetch(tags=True)
            if tag:
                log.info(f"Checking out tag {tag} for {repo}")
                repo.git.checkout(tag)
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
            plugin_root = self.comfy_root / "custom_nodes" / plugin_name
            plugin.update({"root": plugin_root})
            git_clone(
                url=plugin["url"],
                dest=plugin_root,
                tag=plugin["tag"],
            )

    def configure_extra_models(self):
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
            self.__copy_extra_models(extra_models_map)
        else:
            self.__reference_extra_models(extra_models_map)

    def __copy_extra_models(self, extra_models_map: dict[str, Path]):
        for model_key, model_dir in extra_models_map.items():
            model_dest = self.comfy_root / "models" / model_key
            if not model_dest.exists():
                log.info(f"Copying {model_key} from {model_dir} to {model_dest}")
                shutil.copytree(model_dir, model_dest)
            else:
                log.info(f"Model {model_key} already exists at {model_dest}")

    def __reference_extra_models(self, extra_models_map: dict[str, Path]):
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
        if self.addon_settings.get("use_cpu"):
            log.info("Launching ComfyUI with CPU only.")
            launch_args.append("-useCpu")
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

        # add project name to launch args
        launch_args.append("-projectName")
        launch_args.append(self.tmpl_data["project"]["name"])

        _cmd.extend(launch_args)
        cmd = " ".join([str(arg) for arg in _cmd])
        launch_args = [
            "powershell.exe",
            "-Command",
            f"Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', '{cmd}'",
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
