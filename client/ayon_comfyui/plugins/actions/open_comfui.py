import git
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
        self.run_server()

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
            launch_args.extend(list(plugin_names))

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
