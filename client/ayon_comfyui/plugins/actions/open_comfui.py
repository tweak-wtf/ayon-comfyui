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
    label = "Open ComyUI"
    icon = "robot"
    order = 500

    def is_compatible(self, selection):
        """Return whether the action is compatible with the session"""
        return True

    def process(self, selection, **kwargs):
        # get project anatomy
        anatomy = Anatomy(project_name=selection.project_name)
        tmpl_data = get_template_data(selection.project_entity)
        tmpl_data.update({"root": anatomy.roots})

        addon_settings = ayon_api.get_addon_project_settings(
            ADDON_NAME, ADDON_VERSION, tmpl_data["project"]["name"]
        )

        # clone comfyui
        comfy_root_tmpl = StringTemplate(addon_settings["repo"]["root"])
        comfy_root = Path(comfy_root_tmpl.format_strict(tmpl_data))
        self._git_clone(
            url=addon_settings["repo"]["url"],
            root=comfy_root,
            tag=addon_settings["repo"]["tag"],
        )

        # clone custom nodes
        plugins = addon_settings.get("plugins", [])
        for plugin in plugins:
            plugin_name = Path(plugin["url"]).name[:-4]
            plugin_root = comfy_root / "custom_nodes" / plugin_name
            self._git_clone(
                url=plugin["url"],
                root=plugin_root,
                tag=plugin["tag"],
            )

        # copy checkpoints
        if checkpoints_dir := addon_settings.get("checkpoints_dir"):
            comfy_checkpoints_dir = comfy_root / "models" / "checkpoints"
            for cp in Path(checkpoints_dir).iterdir():
                checkpoint_dest = comfy_checkpoints_dir / cp.name
                if not checkpoint_dest.exists():
                    log.info(f"Copying {cp} to {comfy_checkpoints_dir}")
                    shutil.copyfile(cp, checkpoint_dest)

        # run the server in a new terminal session
        launch_script = Path(__file__).parent / "launch_comfyui.ps1"
        _cmd: list = [launch_script.as_posix()]

        launch_args = []
        if addon_settings.get("use_cpu"):
            log.info("Launching ComfyUI with CPU only.")
            launch_args.append("-useCpu")
        _cmd.extend(launch_args)
        cmd = " ".join([str(arg) for arg in _cmd])
        launch_args = [
            "powershell.exe",
            "-Command",
            f"Start-Process powershell.exe -ArgumentList '-NoExit', '-Command', '{cmd}'",
        ]
        subprocess.Popen(
            launch_args,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=comfy_root,
        )

    def _git_clone(self, url: str, root: Path, tag: str = "") -> git.Repo:
        if not root.exists():
            log.info(f"Cloning {url} to {root}")
            repo = git.Repo.clone_from(url, root)
        else:
            repo = git.Repo(root)

        if tag:
            log.info(f"Checking out tag {tag} for {repo}")
            repo.git.checkout(tag)
        return repo
