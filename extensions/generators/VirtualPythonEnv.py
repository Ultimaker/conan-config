import os
import sys
from io import StringIO
from shutil import which
from pathlib import Path

from conan import ConanFile
from conan.errors import ConanException
from conan.tools.files import copy, save, load
from conan.tools.scm import Version
from conan.tools.env import VirtualRunEnv
import subprocess


class VirtualPythonEnv:
    def __init__(self, conanfile: ConanFile):
        self.conanfile: ConanFile = conanfile

    def generate(self) -> None:
        '''
        Creates a Python venv using the CPython installed by conan, then create a script so that this venv can be easily used
        in Conan commands, and finally install the pip dependencies declared in the conanfile data
        '''
        venv_name = f"{self.conanfile.name}_venv"
        bin_venv_path = "Scripts" if self.conanfile.settings.os == "Windows" else "bin"

        # Check if CPython is added as a dependency use the Conan recipe if available; if not use system interpreter
        try:
            cpython = self.conanfile.dependencies["cpython"]
            py_interp = cpython.conf_info.get("user.cpython:python").replace("\\", "/")
        except KeyError:
            py_interp = sys.executable

        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()
        env_vars = env.vars(self.conanfile, scope="run")

        venv_folder = os.path.abspath(venv_name)

        self.conanfile.output.info(f"Using Python interpreter '{py_interp}' to create Virtual Environment in '{venv_folder}'")
        with env_vars.apply():
            subprocess.run([py_interp, "-m", "venv", "--copies", venv_folder], check=True)

        # Make sure there executable is named the same on all three OSes this allows it to be called with `python`
        # simplifying GH Actions steps
        if self.conanfile.settings.os != "Windows":
            py_interp_venv = Path(venv_folder, bin_venv_path, "python")
            if not py_interp_venv.exists():
                py_interp_venv.hardlink_to(
                    Path(venv_folder, bin_venv_path, Path(sys.executable).stem + Path(sys.executable).suffix))
        else:
            py_interp_venv = Path(venv_folder, bin_venv_path,
                                Path(sys.executable).stem + Path(sys.executable).suffix)

        # Generate a script that mimics the venv activate script but is callable easily in Conan commands
        with env_vars.apply():
            buffer = subprocess.run([py_interp_venv, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], capture_output=True, encoding="utf-8", check=True).stdout
        pythonpath = buffer.splitlines()[-1]

        env.define_path("VIRTUAL_ENV", venv_folder)
        env.prepend_path("PATH", os.path.join(venv_folder, bin_venv_path))
        env.prepend_path("LD_LIBRARY_PATH", os.path.join(venv_folder, bin_venv_path))
        env.prepend_path("DYLD_LIBRARY_PATH", os.path.join(venv_folder, bin_venv_path))
        env.prepend_path("PYTHONPATH", pythonpath)
        env.unset("PYTHONHOME")
        env_vars.save_script("virtual_python_env")

        # Install some base packages
        with env_vars.apply():
            subprocess.run([py_interp_venv, "-m", "pip", "install", "--upgrade", "pip"], check=True)
            subprocess.run([py_interp_venv, "-m", "pip", "install", "wheel", "setuptools"], check=True)

        # if self.conanfile.settings.os != "Windows":
        #     content = f"source {os.path.join(output_folder, 'conan', 'virtual_python_env.sh')}\n" + load(self.conanfile,
        #                                                                                                 os.path.join(
        #                                                                                                     output_folder,
        #                                                                                                     bin_venv_path,
        #                                                                                                     "activate"))
        #     save(self.conanfile, os.path.join(output_folder, bin_venv_path, "activate"), content)

        requirements_core = self._make_pip_requirements_files("core")
        requirements_dev = self._make_pip_requirements_files("dev")
        requirements_installer = self._make_pip_requirements_files("installer")

        self._install_pip_requirements(requirements_core, env_vars, py_interp_venv)

        if self.conanfile.conf.get("user.generator.virtual_python_env:dev_tools", default=False, check_type=bool):
            self._install_pip_requirements(requirements_dev, env_vars, py_interp_venv)

        if self.conanfile.conf.get("user.generator.virtual_python_env:installer_tools", default=False,
                                       check_type=bool):
            self._install_pip_requirements(requirements_installer, env_vars, py_interp_venv)

    def _install_pip_requirements(self, files_paths, env_vars, py_interp_venv):
        with env_vars.apply():
            for file_path in files_paths:
                self.conanfile.output.info(f"Installing pip requirements from {file_path}")
                subprocess.run([py_interp_venv, "-m", "pip", "install", "-r", file_path], check=True)


    def _make_pip_requirements_files(self, suffix):
        actual_os = str(self.conanfile.settings.os)

        pip_requirements = VirtualPythonEnv._populate_pip_requirements(self.conanfile, suffix, actual_os)

        for _, dependency in reversed(self.conanfile.dependencies.host.items()):
            pip_requirements |= VirtualPythonEnv._populate_pip_requirements(dependency, suffix, actual_os)

        # We need to make separate files because pip accepts either files containing hashes for all or none of the packages
        requirements_basic_txt = []
        requirements_hashes_txt = []

        for package_name, package_desc in pip_requirements.items():
            package_requirement = ""
            packages_hashes = []

            if "url" in package_desc:
                package_requirement = f"{package_name}@{package_desc['url']}"
            elif "version" in package_desc:
                package_requirement = f"{package_name}=={package_desc['version']}"
            else:
                package_requirement = package_name

            if "hashes" in package_desc:
                for hash_str in package_desc["hashes"]:
                    packages_hashes.append(f"--hash={hash_str}")

            destination_file = requirements_hashes_txt if len(packages_hashes) > 0 else requirements_basic_txt
            destination_file.append(' '.join([package_requirement] + packages_hashes))

        generated_files = []
        self._make_pip_requirements_file(requirements_basic_txt, "basic", suffix, generated_files)
        self._make_pip_requirements_file(requirements_hashes_txt, "hashes", suffix, generated_files)

        return generated_files


    def _make_pip_requirements_file(self, requirements_txt, requirements_type, suffix, generated_files):
        if len(requirements_txt) > 0:
            file_suffixes = [file_suffix for file_suffix in [suffix, requirements_type] if file_suffix is not None]
            file_path = os.path.abspath(f"pip_requirements_{suffix}_{requirements_type}.txt")
            self.conanfile.output.info(f"Generating pip requirements file at '{file_path}'")
            save(self.conanfile, file_path, "\n".join(requirements_txt))
            generated_files.append(file_path)


    @staticmethod
    def _populate_pip_requirements(conanfile, suffix, actual_os):
        pip_requirements = {}
        data_key = f"pip_requirements_{suffix}"

        if hasattr(conanfile, "conan_data") and data_key in conanfile.conan_data:
            pip_requirements_data = conanfile.conan_data[data_key]
            for system in (system for system in pip_requirements_data if system in ("any_os", actual_os)):
                for package_name, package_desc in pip_requirements_data[system].items():

                    try:
                        actual_package_version = Version(pip_requirements[package_name]["version"])
                    except KeyError:
                        actual_package_version = None

                    new_package_version = Version(package_desc["version"]) if "version" in package_desc else None

                    if (actual_package_version is None or
                            (actual_package_version is not None and new_package_version is not None and new_package_version > actual_package_version)):
                        pip_requirements[package_name] = package_desc

        return pip_requirements
