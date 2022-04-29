import sys

import os
from io import StringIO

from pathlib import Path

from jinja2 import Template

from conan.tools.env import VirtualRunEnv
from conans.model import Generator


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
        if hasattr(self.conanfile, "_python_interpreter"):
            python_interpreter = self.conanfile._python_interpreter
        else:
            python_interpreter = sys.executable

        self.conanfile.run(f"{python_interpreter} -m venv {self.conanfile.build_folder}", env = "conanrun")
        python_interpreter = os.path.join(self.conanfile.build_folder, self._venv_path, "python")

        buffer = StringIO()
        self.conanfile.run(f"""{python_interpreter} -c 'import sysconfig; print(sysconfig.get_path("purelib"))'""", env = "conanrun",
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
                    for req_txt in self.conanfile.requirements_txts:
                        with envvars.apply():
                            self.conanfile.run(
                                f"{python_interpreter} -m pip install -r {os.path.join(self.conanfile.source_folder, req_txt)}",
                                run_environment = True, env = "conanrun")
                else:
                    with envvars.apply():
                        self.conanfile.run(
                            f"{python_interpreter} -m pip install -r {os.path.join(self.conanfile.source_folder, self.conanfile.requirements_txts)}",
                            run_environment = True, env = "conanrun")

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
