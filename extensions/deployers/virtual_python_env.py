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


def deploy(graph, output_folder, **kwargs):
    if graph.root.conanfile.name is None:
        conanfile: ConanFile = graph.nodes[1].conanfile
    else:
        conanfile: ConanFile = graph.root.conanfile
    if output_folder is None:
        output_folder = "venv"

    bin_venv_path = "Scripts" if conanfile.settings.os == "Windows" else "bin"

    # Check if CPython is added as a dependency use the Conan recipe if available; if not use system interpreter
    try:
        cpython = conanfile.dependencies["cpython"]
        py_interp = cpython.conf_info.get("user.cpython:python").replace("\\", "/")
    except KeyError:
        py_interp = sys.executable

    vr = VirtualRunEnv(conanfile)
    env = vr.environment()
    sys_vars = env.vars(conanfile, scope="run")

    conanfile.output.info(f"Using Python interpreter '{py_interp}' to create Virtual Environment in '{output_folder}'")
    with sys_vars.apply():
        conanfile.run(f"""{py_interp} -m venv --copies {output_folder}""", env="conanrun", scope="run")

    # Make sure there executable is named the same on all three OSes this allows it to be called with `python`
    # simplifying GH Actions steps
    if conanfile.settings.os != "Windows":
        py_interp_venv = Path(output_folder, bin_venv_path, "python")
        if not py_interp_venv.exists():
            py_interp_venv.hardlink_to(
                Path(output_folder, bin_venv_path, Path(sys.executable).stem + Path(sys.executable).suffix))
    else:
        py_interp_venv = Path(output_folder, bin_venv_path,
                              Path(sys.executable).stem + Path(sys.executable).suffix)

    buffer = StringIO()
    outer = '"' if conanfile.settings.os == "Windows" else "'"
    inner = "'" if conanfile.settings.os == "Windows" else '"'
    with sys_vars.apply():
        conanfile.run(
            f"""{py_interp_venv} -c {outer}import sysconfig; print(sysconfig.get_path({inner}purelib{inner})){outer}""",
            env="conanrun",
            stdout=buffer)
    pythonpath = buffer.getvalue().splitlines()[-1]

    env.define_path("VIRTUAL_ENV", output_folder)
    env.prepend_path("PATH", os.path.join(output_folder, bin_venv_path))
    env.prepend_path("LD_LIBRARY_PATH", os.path.join(output_folder, bin_venv_path))
    env.prepend_path("DYLD_LIBRARY_PATH", os.path.join(output_folder, bin_venv_path))
    env.prepend_path("PYTHONPATH", pythonpath)
    env.unset("PYTHONHOME")
    venv_vars = env.vars(graph.root.conanfile, scope="run")
    venv_vars.save_script("virtual_python_env")

    # Install some base_packages
    with venv_vars.apply():
        conanfile.run(f"""{py_interp_venv} -m pip install wheel setuptools""", env="conanrun")

    if conanfile.settings.os != "Windows":
        content = f"source {os.path.join(output_folder, 'conan', 'virtual_python_env.sh')}\n" + load(graph.root.conanfile,
                                                                                                     os.path.join(
                                                                                                         output_folder,
                                                                                                         bin_venv_path,
                                                                                                         "activate"))
        save(graph.root.conanfile, os.path.join(output_folder, bin_venv_path, "activate"), content)

    pip_requirements = {}
    if conanfile.conan_data is not None and "pip_requirements" in conanfile.conan_data:
        for system in (system for system in conanfile.conan_data["pip_requirements"] if system in ("any", str(conanfile.settings.os))):
            for name, req in conanfile.conan_data["pip_requirements"][system].items():
                if name not in pip_requirements or Version(pip_requirements[name]["version"]) < Version(req["version"]):
                    pip_requirements[name] = req

    for name, dep in reversed(graph.root.conanfile.dependencies.host.items()):
        if dep.conan_data is None:
            continue
        if "pip_requirements" in dep.conan_data:
            for oses in ("any", str(conanfile.settings.os)):
                for name, req in conanfile.conan_data["pip_requirements"][oses].items():
                    if name not in pip_requirements or Version(pip_requirements[name]["version"]) < Version(
                            req["version"]):
                        pip_requirements[name] = req

    requirements_txt = ""
    for name, req in pip_requirements.items():
        if "url" in req:
            requirements_txt += f"{req['url']}"
        else:
            requirements_txt += f"{name}=={req['version']}"
        for hash_str in req['hashes']:
            requirements_txt += f" --hash={hash_str}"
        requirements_txt += "\n"

    pip_requirements_path = os.path.join(output_folder, 'conan', 'requirements.txt')
    save(graph.root.conanfile, pip_requirements_path, requirements_txt)
    with venv_vars.apply():
        conanfile.run(f"{py_interp_venv} -m pip install -r {pip_requirements_path}",
                      env="conanrun")

    if conanfile.conf.get("user.deployer.virtual_python_env:dev_tools", default = False, check_type = bool):
        if "pip_requirements_dev" in conanfile.conan_data:
            pip_requirements_dev = conanfile.conan_data["pip_requirements_dev"]
            pip_requirements_dev_path = os.path.join(output_folder, 'conan', 'requirements_dev.txt')
            save(graph.root.conanfile, pip_requirements_dev_path, '\n'.join(pip_requirements_dev))
            with venv_vars.apply():
                conanfile.run(f"{py_interp_venv} -m pip install -r {pip_requirements_dev_path}", env="conanrun")
