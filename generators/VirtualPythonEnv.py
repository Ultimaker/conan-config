import sys

import os
from io import StringIO

from pathlib import Path

from jinja2 import Template

from conan.tools.env import VirtualRunEnv
from conans.model import Generator
from conans.errors import ConanException


class VirtualPythonEnv(Generator):
    @property
    def _script_ext(self):
        if self.conanfile.settings.get_safe("os") == "Windows":
            return ".ps1"
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
        python_interpreter = Path(self.conanfile.deps_user_info["cpython"].python)

        # When on Windows execute as Windows Path
        if self.conanfile.settings.os == "Windows":
            python_interpreter = Path(*[f'"{p}"' if " " in p else p for p in python_interpreter.parts])

        # Create the virtual environment
        if self.conanfile.in_local_cache:
            venv_folder = self.conanfile.install_folder
        else:
            venv_folder = self.conanfile.build_folder if self.conanfile.build_folder else Path(os.getcwd(), "venv")

        self.conanfile.output.info(f"Creating virtual environment in {venv_folder}")
        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()
        sys_vars = env.vars(self.conanfile, scope = "run")

        with sys_vars.apply():
            self.conanfile.run(f"""{python_interpreter} -m venv {venv_folder}""", scope = "run")

        # Make sure there executable is named the same on all three OSes this allows it to be called with `python`
        # simplifying GH Actions steps
        if self.conanfile.settings.os != "Windows":
            python_venv_interpreter = Path(venv_folder, self._venv_path, "python")
            if not python_venv_interpreter.exists():
                python_venv_interpreter.hardlink_to(
                    Path(venv_folder, self._venv_path, Path(sys.executable).stem + Path(sys.executable).suffix))
        else:
            python_venv_interpreter = Path(venv_folder, self._venv_path, Path(sys.executable).stem + Path(sys.executable).suffix)

        if not python_venv_interpreter.exists():
            raise ConanException(f"Virtual environment Python interpreter not found at: {python_venv_interpreter}")
        if self.conanfile.settings.os == "Windows":
            python_venv_interpreter = Path(*[f'"{p}"' if " " in p else p for p in python_venv_interpreter.parts])

        buffer = StringIO()
        outer = '"' if self.conanfile.settings.os == "Windows" else "'"
        inner = "'" if self.conanfile.settings.os == "Windows" else '"'
        with sys_vars.apply():
            self.conanfile.run(f"""{python_venv_interpreter} -c {outer}import sysconfig; print(sysconfig.get_path({inner}purelib{inner})){outer}""",
                          env = "conanrun",
                          output = buffer)
        pythonpath = buffer.getvalue().splitlines()[-1]

        if hasattr(self.conanfile, f"_{self.conanfile.name}_run_env"):
            project_run_env = getattr(self.conanfile, f"_{self.conanfile.name}_run_env")
            if project_run_env:
                env.compose_env(project_run_env)  # TODO: Add logic for dependencies

        env.define_path("VIRTUAL_ENV", venv_folder)
        env.prepend_path("PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("LD_LIBRARY_PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("DYLD_LIBRARY_PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("PYTHONPATH", pythonpath)
        env.unset("PYTHONHOME")
        venv_vars = env.vars(self.conanfile, scope = "run")

        # Install some base_packages
        with venv_vars.apply():
            self.conanfile.run(f"""{python_venv_interpreter} -m pip install wheel setuptools""", env = "conanrun")

        # Install pip_requirements from dependencies
        for dep_name in reversed(self.conanfile.deps_user_info):
            dep_user_info = self.conanfile.deps_user_info[dep_name]
            if len(dep_user_info.vars) == 0:
                continue
            pip_req_paths = [self.conanfile.deps_cpp_info[dep_name].res_paths[i] for i, req_path in
                             enumerate(self.conanfile.deps_cpp_info[dep_name].resdirs) if req_path.endswith("pip_requirements")]
            if len(pip_req_paths) != 1:
                continue
            pip_req_base_path = Path(pip_req_paths[0])
            if hasattr(dep_user_info, "pip_requirements"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements)
                if req_txt.exists():
                    with venv_vars.apply():
                        self.conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --upgrade", env = "conanrun")
                    self.conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements in user_info installed!")
                else:
                    self.conanfile.output.warn(f"Dependency {dep_name} specifies pip_requirements in user_info but {req_txt} can't be found!")

            if hasattr(dep_user_info, "pip_requirements_git"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements_git)
                if req_txt.exists():
                    with venv_vars.apply():
                        self.conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --upgrade", env = "conanrun")
                    self.conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements_git in user_info installed!")
                else:
                    self.conanfile.output.warn(
                        f"Dependency {dep_name} specifies pip_requirements_git in user_info but {req_txt} can't be found!")

            if hasattr(dep_user_info, "pip_requirements_build"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements_build)
                if req_txt.exists():
                    with venv_vars.apply():
                        self.conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --upgrade", env = "conanrun")
                    self.conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements_build in user_info installed!")
                else:
                    self.conanfile.output.warn(
                        f"Dependency {dep_name} specifies pip_requirements_build in user_info but {req_txt} can't be found!")

        if not self.conanfile.in_local_cache and hasattr(self.conanfile, "requirements_txts"):
            # Install the Python requirements of the current conanfile requirements*.txt
            pip_req_base_path = Path(self.conanfile.source_folder)

            for req_path in sorted(self.conanfile.requirements_txts, reverse = True):
                req_txt = pip_req_base_path.joinpath(req_path)
                if req_txt.exists():
                    with venv_vars.apply():
                        self.conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --upgrade", env = "conanrun")
                    self.conanfile.output.success(f"Requirements file {req_txt} installed!")
                else:
                    self.conanfile.output.warn(f"Requirements file {req_txt} can't be found!")

        # Add all dlls/dylibs/so found in site-packages to the PATH, DYLD_LIBRARY_PATH and LD_LIBRARY_PATH
        dll_paths = list({ dll.parent for dll in Path(pythonpath).glob("**/*.dll") })
        for dll_path in dll_paths:
            env.append_path("PATH", str(dll_path))

        dylib_paths = list({ dylib.parent for dylib in Path(pythonpath).glob("**/*.dylib") })
        for dylib_path in dylib_paths:
            env.append_path("DYLD_LIBRARY_PATH", str(dylib_path))

        so_paths = list({ so.parent for so in Path(pythonpath).glob("**/*.dylib") })
        for so_path in so_paths:
            env.append_path("LD_LIBRARY_PATH", str(so_path))

        full_envvars = env.vars(self.conanfile, scope = "conanrun")

        # Generate the Python Virtual Environment Script
        full_envvars.save_sh(Path(venv_folder, self._venv_path, "activate"))
        full_envvars.save_bat(Path(venv_folder, self._venv_path, "activate.bat"))
        full_envvars.save_ps1(Path(venv_folder, self._venv_path, "Activate.ps1"))

        # Generate the GitHub Action activation script
        env_prefix = "Env:" if self.conanfile.settings.os == "Windows" else ""
        activate_github_actions_buildenv = Template(r"""{% for var, value in envvars.items() %}echo "{{ var }}={{ value }}" >> ${{ env_prefix }}GITHUB_ENV
{% endfor %}""").render(envvars = full_envvars, env_prefix = env_prefix)

        return {
            str(Path(venv_folder, self._venv_path, f"activate_github_actions_env{self._script_ext}")): activate_github_actions_buildenv
        }
