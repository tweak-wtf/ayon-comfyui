
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
        # log.debug(dir(self))
        # log.debug(f"{self.data = }")
        # log.debug(dir(self.manager))

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
        pass

    def configure_extra_models(self):
        pass

    def run_server(self):
        launch_script = ADDON_ROOT / "tools" / "install_and_run_server_venv.ps1"

        _cmd: list = [launch_script.as_posix()]

        launch_args = []
        if self.addon_settings.get("use_cpu"):
            log.info("Launching ComfyUI with CPU only.")
            launch_args.append("-useCpu")
        # if self.plugins:
        #     launch_args.append("-plugins")
        #     plugin_names = [plugin["root"].name for plugin in self.plugins]
        #     launch_args.append(",".join(plugin_names))
        # if self.extra_dependencies:
        #     launch_args.append("-extraDependencies")
        #     launch_args.append(",".join(self.extra_dependencies))
        # if self.cache_dir:
        #     launch_args.append("-cacheDir")
        #     launch_args.append(self.cache_dir)

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
            # "shell": True,
            # "text": True,
            # "stdout": subprocess.PIPE,
            # "stderr": subprocess.PIPE,
            "stdout": None,
            "stderr": None,
            "cwd": self.comfy_root,
            "env": env,
            "creationflags": subprocess.CREATE_NEW_CONSOLE,
        }

        self.launch_context.launch_args = launch_args
        self.launch_context.kwargs = popen_kwargs
