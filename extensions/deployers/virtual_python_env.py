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


def populate_pip_requirements(key, pip_requirements, conan_data, actual_os):
    if conan_data is not None and key in conan_data:
        for system in (system for system in conan_data[key] if system in ("any", actual_os)):
            for name, req in conan_data[key][system].items():
                if name not in pip_requirements or Version(pip_requirements[name]["version"]) < Version(req["version"]):
                    pip_requirements[name] = req


def populate_full_pip_requirements(conanfile, key, pip_requirements, actual_os):
    populate_pip_requirements(key, pip_requirements, conanfile.conan_data, actual_os)

    for name, dep in reversed(conanfile.dependencies.host.items()):
        populate_pip_requirements(key, pip_requirements, dep.conan_data, actual_os)


def install_pip_requirements(file_suffix, file_content, output_folder, conanfile, venv_vars, py_interp_venv):
    if len(file_content) > 0:
        pip_file_path = os.path.join(output_folder, 'conan', f'requirements_{file_suffix}.txt')
        save(conanfile, pip_file_path, "\n".join(file_content))
        with venv_vars.apply():
            conanfile.run(f"{py_interp_venv} -m pip install -r {pip_file_path}", env="conanrun")


def deploy(graph, output_folder, **kwargs):
    if graph.root.conanfile.name is None:
        conanfile: ConanFile = graph.nodes[1].conanfile
    else:
        conanfile: ConanFile = graph.root.conanfile

    if output_folder is None:
        output_folder = "venv"
    else:
        output_folder = str(Path(output_folder, "venv"))

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
    populate_full_pip_requirements(conanfile, "pip_requirements", pip_requirements, str(conanfile.settings.os))

    requirements_hashed_txt = []
    requirements_url_txt = []
    for name, req in pip_requirements.items():
        if "url" in req:
            requirements_url_txt.append(req['url'])
        else:
            requirement_txt = [f"{name}=={req['version']}"]

            if "hashes" in req:
                for hash_str in req['hashes']:
                    requirement_txt.append(f"--hash={hash_str}")

            requirements_hashed_txt.append(" ".join(requirement_txt))

    install_pip_requirements("hashed", requirements_hashed_txt, output_folder, conanfile, venv_vars, py_interp_venv)
    install_pip_requirements("url", requirements_url_txt, output_folder, conanfile, venv_vars, py_interp_venv)

    if conanfile.conf.get("user.deployer.virtual_python_env:dev_tools", default = False, check_type = bool) and conanfile.conan_data is not None and "pip_requirements_dev" in conanfile.conan_data:
        install_pip_requirements("dev", conanfile.conan_data["pip_requirements_dev"], output_folder, conanfile, venv_vars, py_interp_venv)
