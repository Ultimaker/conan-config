import sys

import os
from io import StringIO

from pathlib import Path

from jinja2 import Template

from conan import ConanFile
from conan.tools.env import VirtualRunEnv
from conans.model import Generator
from conans.errors import ConanException


class VirtualPythonEnv(Generator):

    @property
    def _script_ext(self):
        if self.conanfile.settings.get_safe("os") == "Windows":
            if self.conanfile.conf.get("tools.env.virtualenv:powershell", check_type = bool):
                return ".ps1"
            else:
                return ".bat"
        return ".sh"

    @property
    def _venv_path(self):
        if self.settings.os == "Windows":
            return "Scripts"
        return "bin"

    @property
    def filename(self):
        pass

    @property
    def content(self):
        conanfile: ConanFile = self.conanfile
        python_interpreter = Path(self.conanfile.deps_user_info["cpython"].python)

        # When on Windows execute as Windows Path
        if conanfile.settings.os == "Windows":
            python_interpreter = Path(*[f'"{p}"' if " " in p else p for p in python_interpreter.parts])

        # Create the virtual environment
        if conanfile.install_folder is None:
            if conanfile.build_folder is None:
                venv_folder = Path(os.getcwd(), "venv")
            else:
                venv_folder = conanfile.build_folder
        else:
            venv_folder = conanfile.install_folder
        conanfile.run(f"""{python_interpreter} -m venv {venv_folder}""", run_environment = True, env = "conanrun")

        # Make sure there executable is named the same on all three OSes this allows it to be called with `python`
        # simplifying GH Actions steps
        if conanfile.settings.os != "Windows":
            python_venv_interpreter = Path(venv_folder, self._venv_path, "python")
            if not python_venv_interpreter.exists():
                python_venv_interpreter.hardlink_to(
                    Path(venv_folder, self._venv_path, Path(sys.executable).stem + Path(sys.executable).suffix))
        else:
            python_venv_interpreter = Path(venv_folder, self._venv_path, Path(sys.executable).stem + Path(sys.executable).suffix)

        if not python_venv_interpreter.exists():
            raise ConanException(f"Virtual environment Python interpreter not found at: {python_venv_interpreter}")
        if conanfile.settings.os == "Windows":
            python_venv_interpreter = Path(*[f'"{p}"' if " " in p else p for p in python_venv_interpreter.parts])

        buffer = StringIO()
        outer = '"' if conanfile.settings.os == "Windows" else "'"
        inner = "'" if conanfile.settings.os == "Windows" else '"'
        conanfile.run(f"{python_venv_interpreter} -c {outer}import sysconfig; print(sysconfig.get_path({inner}purelib{inner})){outer}",
                      env = "conanrun",
                      output = buffer)
        pythonpath = buffer.getvalue().splitlines()[-1]

        run_env = VirtualRunEnv(conanfile)
        env = run_env.environment()

        env.define_path("VIRTUAL_ENV", venv_folder)
        env.prepend_path("PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("PYTHONPATH", pythonpath)
        env.unset("PYTHONHOME")

        envvars = env.vars(self.conanfile, scope = "run")

        # Install some base_packages
        conanfile.run(f"""{python_venv_interpreter} -m pip install wheel setuptools""", run_environment = True, env = "conanrun")

        # Install pip_requirements from dependencies
        for dep_name in reversed(conanfile.deps_user_info):
            dep_user_info = conanfile.deps_user_info[dep_name]
            if len(dep_user_info.vars) == 0:
                continue
            pip_req_paths = [conanfile.deps_cpp_info[dep_name].res_paths[i] for i, req_path in
                             enumerate(conanfile.deps_cpp_info[dep_name].resdirs) if req_path == "pip_requirements"]
            if len(pip_req_paths) != 1:
                continue
            pip_req_base_path = Path(pip_req_paths[0])
            if hasattr(dep_user_info, "pip_requirements"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements)
                if req_txt.exists():
                    conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --force-reinstall", run_environment = True,
                                  env = "conanrun")
                    conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements in user_info installed!")
                else:
                    conanfile.output.warn(f"Dependency {dep_name} specifies pip_requirements in user_info but {req_txt} can't be found!")

            if hasattr(dep_user_info, "pip_requirements_git"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements_git)
                if req_txt.exists():
                    conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --force-reinstall", run_environment = True,
                                  env = "conanrun")
                    conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements_git in user_info installed!")
                else:
                    conanfile.output.warn(
                        f"Dependency {dep_name} specifies pip_requirements_git in user_info but {req_txt} can't be found!")

        if not conanfile.in_local_cache:
            # Install the Python requirements of the current conanfile requirements*.txt
            pip_req_base_path = Path(conanfile.cpp_info.rootpath, conanfile.cpp_info.resdirs[-1])
            # Add the dev reqs needed for pyinstaller
            conanfile.run(
                f"{python_venv_interpreter} -m pip install -r {pip_req_base_path.joinpath(conanfile.user_info.pip_requirements_build)} --force-reinstall",
                run_environment = True, env = "conanrun")

            # Install the requirements.text for cura
            conanfile.run(
                f"{python_venv_interpreter} -m pip install -r {pip_req_base_path.joinpath(conanfile.user_info.pip_requirements_git)} --force-reinstall",
                run_environment = True, env = "conanrun")
            # Do the final requirements last such that these dependencies takes precedence over possible previous installed Python modules.
            # Since these are actually shipped with Cura and therefore require hashes and pinned version numbers in the requirements.txt
            self.run(
                f"{python_venv_interpreter} -m pip install -r {pip_req_base_path.joinpath(conanfile.user_info.pip_requirements)} --force-reinstall",
                run_environment = True,
                env = "conanrun")

        # Generate the Python Virtual Environment Script
        with open(Path(__file__).parent.joinpath("VirtualPythonEnvResources", "activate.bat.jinja"), "r") as f:
            activate_bat = Template(f.read()).render(envvars = envvars, prompt = self.conanfile.name)

        with open(Path(__file__).parent.joinpath("VirtualPythonEnvResources", "deactivate.bat.jinja"), "r") as f:
            deactivate_bat = Template(f.read()).render(envvars = envvars)

        with open(Path(__file__).parent.joinpath("VirtualPythonEnvResources", "Activate.ps1.jinja"), "r") as f:
            activate_ps1 = Template(f.read()).render(envvars = envvars, prompt = self.conanfile.name)

        with open(Path(__file__).parent.joinpath("VirtualPythonEnvResources", "activate.jinja"), "r") as f:
            activate_sh = Template(f.read()).render(envvars = envvars, prompt = self.conanfile.name)

        with open(Path(__file__).parent.joinpath("VirtualPythonEnvResources", "activate_github_actions_buildenv.jinja"), "r") as f:
            env_prefix = "Env:" if self.conanfile.settings.os == "Windows" else ""
            activate_github_actions_buildenv = Template(f.read()).render(envvars = envvars, env_prefix = env_prefix)

        return {
            str(Path(venv_folder, self._venv_path, "activate.bat")): activate_bat,
            str(Path(venv_folder, self._venv_path, "deactivate.bat.jinja")): deactivate_bat,
            str(Path(venv_folder, self._venv_path, "Activate.ps1")): activate_ps1,
            str(Path(venv_folder, self._venv_path, "activate")): activate_sh,
            str(Path(venv_folder, self._venv_path, f"activate_github_actions_env{self._script_ext}")): activate_github_actions_buildenv
        }
