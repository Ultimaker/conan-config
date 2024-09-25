from pathlib import Path
from typing import Dict

from jinja2 import Template
from conan import ConanFile
from conan.tools.scm import Version
from conan.tools.files import save
from conan.tools.env.virtualrunenv import VirtualRunEnv


class PyCharmRunEnv:
    def __init__(self, conanfile: ConanFile):
        self.conanfile: ConanFile = conanfile
        self.settings = self.conanfile.settings

    @property
    def _base_dir(self):
        return Path("$PROJECT_DIR$", "venv")

    @property
    def _py_interp(self):
        if self.settings.os == "Windows":
            py_interp = Path(
                *[f'"{p}"' if " " in p else p for p in self._base_dir.joinpath("Scripts", "python.exe").parts])
            return py_interp
        return self._base_dir.joinpath("bin", "python")

    @property
    def _site_packages(self):
        if self.settings.os == "Windows":
            return self._base_dir.joinpath("Lib", "site-packages")
        py_version = Version(self.conanfile.dependencies["cpython"].ref.version)
        return self._base_dir.joinpath("lib", f"python{py_version.major}.{py_version.minor}", "site-packages")

    def generate(self) -> None:
        if self.conanfile.conan_data is None or "pycharm_targets" not in self.conanfile.conan_data:
            # There are no _pycharm_targets in the conanfile for the package using this generator.
            return

        # Collect environment variables for use in the template
        env = VirtualRunEnv(self.conanfile).environment()
        env.prepend_path("PYTHONPATH", str(self._site_packages))

        if hasattr(self.conanfile, f"_{self.conanfile.name}_run_env"):
            project_run_env = getattr(self.conanfile, f"_{self.conanfile.name}_run_env")
            if project_run_env:
                env.compose_env(project_run_env)  # TODO: Add logic for dependencies

        # Create Pycharm run configuration from template for each target
        for target in self.conanfile.conan_data["pycharm_targets"]:
            target["env_vars"] = env.vars(self.conanfile, scope="run")
            target["sdk_path"] = str(self._py_interp)
            if "parameters" not in target:
                target["parameters"] = ""

            with open(Path(self.conanfile.source_folder, target["jinja_path"]), "r") as f:
                template = Template(f.read())
                run_configuration = template.render(target)
                save(self.conanfile, Path(".run", f"{target['name']}.run.xml"), run_configuration)
