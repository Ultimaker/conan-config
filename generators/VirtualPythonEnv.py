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
        conanfile: ConanFile = self.conanfile
        python_interpreter = Path(self.conanfile.deps_user_info["cpython"].python)

        # When on Windows execute as Windows Path
        if conanfile.settings.os == "Windows":
            python_interpreter = Path(*[f'"{p}"' if " " in p else p for p in python_interpreter.parts])

        # Create the virtual environment
        print(f"Creating virtual environment in {conanfile.install_folder}")
        print(f"Creating virtual environment in {conanfile.build_folder}")
        if conanfile.in_local_cache:
            venv_folder = conanfile.install_folder
        else:
            venv_folder = conanfile.build_folder if conanfile.build_folder else  Path(os.getcwd(), "venv")

        conanfile.output.info(f"Creating virtual environment in {venv_folder}")
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
        env.prepend_path("LD_LIBRARY_PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("DYLD_LYBRARY_PATH", os.path.join(venv_folder, self._venv_path))
        env.prepend_path("PYTHONPATH", pythonpath)
        env.unset("PYTHONHOME")

        envvars = env.vars(conanfile, scope = "run")

        # Install some base_packages
        conanfile.run(f"""{python_venv_interpreter} -m pip install wheel setuptools""", run_environment = True, env = "conanrun")

        # Install pip_requirements from dependencies
        for dep_name in reversed(conanfile.deps_user_info):
            dep_user_info = conanfile.deps_user_info[dep_name]
            if len(dep_user_info.vars) == 0:
                continue
            pip_req_paths = [conanfile.deps_cpp_info[dep_name].res_paths[i] for i, req_path in
                             enumerate(conanfile.deps_cpp_info[dep_name].resdirs) if req_path.endswith("pip_requirements")]
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

            if hasattr(dep_user_info, "pip_requirements_build"):
                req_txt = pip_req_base_path.joinpath(dep_user_info.pip_requirements_build)
                if req_txt.exists():
                    conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --force-reinstall", run_environment = True,
                                  env = "conanrun")
                    conanfile.output.success(f"Dependency {dep_name} specifies pip_requirements_build in user_info installed!")
                else:
                    conanfile.output.warn(
                        f"Dependency {dep_name} specifies pip_requirements_build in user_info but {req_txt} can't be found!")

        if not conanfile.in_local_cache and hasattr(conanfile, "requirements_txts"):
            # Install the Python requirements of the current conanfile requirements*.txt
            pip_req_base_path = Path(conanfile.source_folder)

            for req_path in sorted(conanfile.requirements_txts, reverse = True):
                req_txt = pip_req_base_path.joinpath(req_path)
                if req_txt.exists():
                    conanfile.run(f"{python_venv_interpreter} -m pip install -r {req_txt} --force-reinstall", run_environment = True,
                                  env = "conanrun")
                    conanfile.output.success(f"Requirements file {req_txt} installed!")
                else:
                    conanfile.output.warn(f"Requirements file {req_txt} can't be found!")

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

        full_envvars = env.vars(conanfile, scope = "run")

        # Generate the Python Virtual Environment Script
        full_envvars.save_sh(Path(venv_folder, self._venv_path, "activate"))
        full_envvars.save_bat(Path(venv_folder, self._venv_path, "activate.bat"))
        full_envvars.save_ps1(Path(venv_folder, self._venv_path, "Activate.ps1"))

        # Generate the GitHub Action activation script
        env_prefix = "Env:" if conanfile.settings.os == "Windows" else ""
        activate_github_actions_buildenv = Template(r"""{% for var, value in envvars.items() %}echo "{{ var }}={{ value }}" >> ${{ env_prefix }}GITHUB_ENV
{% endfor %}""").render(envvars = full_envvars, env_prefix = env_prefix)

        return {
            str(Path(venv_folder, self._venv_path, f"activate_github_actions_env{self._script_ext}")): activate_github_actions_buildenv
        }
