import sys

import os
from io import StringIO

from pathlib import Path

from jinja2 import Template

from conan.tools.env import VirtualRunEnv
from conans.model import Generator
from conans.errors import ConanException
from conans import tools


class VirtualPythonEnv(Generator):

    @property
    def _venv_path(self):
        if self.settings.os == "Windows":
            return "Scripts"
        return "bin"

    @property
    def filename(self):
        filepath = str(Path(self.conanfile.generators_folder).joinpath("activate"))
        if self.conanfile.settings.get_safe("os") == "Windows":
            if self.conanfile.conf.get("tools.env.virtualenv:powershell", check_type = bool):
                filepath += ".ps1"
            else:
                filepath += ".bat"
        return filepath

    @property
    def content(self):
        from platform import python_version
        py_version = python_version()
        py_version = self.conanfile.options.get_safe("python_version", py_version)
        if py_version == python_version():
            python_interpreter = Path(sys.executable)
        else:
            # Need to find the requested Python version
            # Assuming they're all installed along-side each other
            current_py_base_version = f"{tools.Version(python_version()).major}{tools.Version(python_version()).minor}"
            py_base_version = f"{tools.Version(py_version).major}{tools.Version(py_version).minor}"
            base_exec_prefix = sys.exec_prefix.split(current_py_base_version)
            if len(base_exec_prefix) != 2:
                raise ConanException(f"Could not find requested Python version {py_version}")
            py_exec_prefix = Path(base_exec_prefix[0] + py_base_version)
            py_exec = Path(sys.executable)
            python_interpreter = py_exec_prefix.joinpath(py_exec.stem + py_exec.suffix)
            if not python_interpreter.exists():
                raise ConanException(f"Could not find requested Python executable at: {python_interpreter}")

        # When on Windows execute as Windows Path
        if self.conanfile.settings.os == "Windows":
            python_interpreter = Path(*[f"'{p}'" if " " in p else p for p in python_interpreter.parts])

        # Create the virtual environment
        self.conanfile.run(f"""{python_interpreter} -m venv {self.conanfile.folders.build}""", env = "conanrun")

        #
        python_venv_interpreter = Path(self.conanfile.build_folder, self._venv_path,
                                       Path(sys.executable).stem + Path(sys.executable).suffix)
        if not python_venv_interpreter.exists():
            raise ConanException(f"Virtual environment Python interpreter not found at: {python_venv_interpreter}")
        if self.conanfile.settings.os == "Windows":
            python_venv_interpreter = Path(*[f"'{p}'" if " " in p else p for p in python_venv_interpreter.parts])

        buffer = StringIO()
        self.conanfile.run(f"""{python_venv_interpreter} -c "import sysconfig; print(sysconfig.get_path('purelib'))""""", env = "conanrun",
                           output = buffer)
        pythonpath = buffer.getvalue().splitlines()[-1]

        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()

        env.define_path("VIRTUAL_ENV", self.conanfile.build_folder)
        env.prepend_path("PATH", os.path.join(self.conanfile.build_folder, self._venv_path))
        env.prepend_path("PYTHONPATH", pythonpath)
        env.unset("PYTHONHOME")
        env.define("PS1", f"({self.conanfile.name}) ${{PS1:-}}")

        envvars = env.vars(self.conanfile, scope = "run")

        if hasattr(self.conanfile, "requirements_txts"):
            if self.conanfile.requirements_txts:
                if hasattr(self.conanfile.requirements_txts, "__iter__") and not isinstance(self.conanfile.requirements_txts, str):
                    # conanfile has a list of requirements_txts specified
                    for req_txt in self.conanfile.requirements_txts:
                        with envvars.apply():
                            requirements_txt_path = Path(self.conanfile.source_folder, req_txt)
                            if requirements_txt_path.exists():
                                self.conanfile.run(f"""{python_venv_interpreter} -m pip install -r {requirements_txt_path}""",
                                                   run_environment = True, env = "conanrun",
                                                   win_bash = self.conanfile.settings.os == "Windows")
                            else:
                                self.conanfile.output.warn(f"Failed to find pip requirement file: {requirements_txt_path}")
                else:
                    # conanfile has a single requirements_txt specified
                    with envvars.apply():
                        requirements_txt_path = Path(self.conanfile.source_folder, self.conanfile.requirements_txts)
                        if requirements_txt_path.exists():
                            self.conanfile.run(f"""{python_venv_interpreter} -m pip install -r {requirements_txt_path}""",
                                               run_environment = True, env = "conanrun")
                        else:
                            self.conanfile.output.warn(f"Failed to find pip requirement file: {requirements_txt_path}")
        else:
            # No requirements_txts found in the conanfile looking for a requirements.txt in the source_folder
            requirements_txt_path = Path(self.conanfile.source_folder, "requirements.txt")
            if requirements_txt_path.exists():
                with envvars.apply():
                    self.conanfile.run(f"""{python_venv_interpreter} -m pip install -r {requirements_txt_path}""", run_environment = True,
                                       env = "conanrun")
            else:
                self.conanfile.output.warn(f"Failed to find pip requirement file: {requirements_txt_path}")

        # Generate the Python Virtual Environment Script
        template = Template("""\
deactivate()
{
{% for k, v in envvars.items() %}export {{ k }}=$OLD_{{ k }}
unset OLD_{{ k }}
{% endfor %}}

{% for k, v in envvars.items() %}export OLD_{{ k }}=${{ k }}
export {{ k }}={{ v }}
{% endfor %}""")
        return template.render(envvars = envvars)
