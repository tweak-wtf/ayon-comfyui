import git
import yaml
import shutil
import subprocess
from pathlib import Path

import ayon_api

from ayon_core.pipeline import (
    Anatomy,
    LauncherAction,
)
from ayon_core.pipeline.template_data import get_template_data
from ayon_core.lib import Logger, StringTemplate


from ayon_comfyui import ADDON_NAME, ADDON_VERSION

log = Logger.get_logger(__name__)


class OpenComfyUI(LauncherAction):
    name = "open_comfyui"
    label = "Open ComfyUI"
    icon = "robot"
    order = 500

    def is_compatible(self, selection):
        """Return whether the action is compatible with the session"""
        return True

    def process(self, selection, **kwargs):
        self.pre_process(selection)
        self.clone_repositories()
        self.configure_extra_models()
        self.run_server()  # TODO: get pid

    def pre_process(self, selection):
        # get project anatomy
        anatomy = Anatomy(project_name=selection.project_name)
        tmpl_data = get_template_data(selection.project_entity)
        tmpl_data.update({"root": anatomy.roots})

        self.addon_settings = ayon_api.get_addon_project_settings(
            ADDON_NAME, ADDON_VERSION, tmpl_data["project"]["name"]
        )

        comfy_root_tmpl = StringTemplate(
            self.addon_settings["repositories"]["base_template"]
        )
        self.comfy_root = Path(comfy_root_tmpl.format_strict(tmpl_data))

        self.plugins = self.addon_settings["repositories"]["plugins"]
        self.extra_dependencies = set()
        for plugin in self.plugins:
            if plugin.get("extra_dependencies"):
                self.extra_dependencies.update(plugin["extra_dependencies"])

        addon_extra_models = self.addon_settings["general"]["extra_models"]
        self.extra_models = {
            model_key: model_settings
            for model_key, model_settings in addon_extra_models.items()
            if model_settings.get("enabled")
        }

    def clone_repositories(self):
        def git_clone(url: str, dest: Path, tag: str = "") -> git.Repo:
            if not dest.exists():
                log.info(f"Cloning {url} to {dest}")
                repo = git.Repo.clone_from(url, dest)
            else:
                repo = git.Repo(dest)

            if tag:
                log.info(f"Checking out tag {tag} for {repo}")
                repo.git.checkout(tag)
            return repo

        base_repo = self.addon_settings["repositories"]["base"]
        git_clone(
            url=base_repo["url"],
            dest=self.comfy_root,
            tag=base_repo["tag"],
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
        if not self.extra_models:
            return

        # get server settings
        extra_model_paths = {}
        for model_key, model_settings in self.extra_models.items():
            if not model_settings.get("dir_templates"):
                continue

            if model_settings.get("copy_to_base"):
                for tmpl in model_settings["dir_templates"]:
                    # TODO: resolve templates
                    log.info(f"Copying {model_key} from {tmpl} to ComfyUI base")
                    for model in Path(tmpl).iterdir():
                        model_dest = self.comfy_root / "models" / model_key / model.name
                        if not model_dest.exists():
                            shutil.copyfile(model, model_dest)
            else:
                # TODO: convert to multiline string using | operator
                dirs = "\n".join(model_settings["dir_templates"])
                extra_model_paths.update({model_key: dirs})

        # read current settings
        config_file = self.comfy_root / "extra_model_paths.yaml"
        with config_file.open("r") as config_reader:
            config = yaml.safe_load(config_reader)
            log.info(f"Current config: {config}")

        # write new config if configured
        if extra_model_paths:
            new_conf = config.copy() if config else {}
            new_conf.update({"comfyui": extra_model_paths})

            with config_file.open("w+") as config_writer:
                yaml.safe_dump(new_conf, config_writer)

    def copy_checkpoints(self):
        # copy checkpoints
        if checkpoints_dir := self.addon_settings.get("checkpoints_dir"):
            comfy_checkpoints_dir = self.comfy_root / "models" / "checkpoints"
            for cp in Path(checkpoints_dir).iterdir():
                checkpoint_dest = comfy_checkpoints_dir / cp.name
                if not checkpoint_dest.exists():
                    log.info(f"Copying {cp} to {comfy_checkpoints_dir}")
                    shutil.copyfile(cp, checkpoint_dest)

    def run_server(self):
        # run the server in a new terminal session
        launch_script = Path(__file__).parent / "launch_comfyui.ps1"
        _cmd: list = [launch_script.as_posix()]

        launch_args = []
        if self.addon_settings["general"].get("use_cpu"):
            log.info("Launching ComfyUI with CPU only.")
            launch_args.append("-useCpu")
        if self.plugins:
            launch_args.append("-plugins")
            plugin_names = [plugin["root"].name for plugin in self.plugins]
            launch_args.append(",".join(plugin_names))
        if self.extra_dependencies:
            launch_args.append("-extraDependencies")
            launch_args.append(",".join(self.extra_dependencies))

        _cmd.extend(launch_args)
        cmd = " ".join([str(arg) for arg in _cmd])
        launch_args = [
            "powershell.exe",
            "-Command",
            f"Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', '{cmd}'",
        ]
        log.info(f"{cmd = }")
        subprocess.Popen(
            launch_args,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.comfy_root,
        )
