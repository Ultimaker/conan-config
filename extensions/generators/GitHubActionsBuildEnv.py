from pathlib import Path

from jinja2 import Template

from conan import ConanFile
from conan.tools.env import VirtualBuildEnv
from conan.tools.files import save


class GitHubActionsBuildEnv:
    def __init__(self, conanfile: ConanFile):
        self.conanfile: ConanFile = conanfile
        self.settings = self.conanfile.settings

    def generate(self):
        template = Template(
            """{% for k, v in envvars.items() %}echo "{{ k }}={{ v }}" >> ${{ env_prefix }}GITHUB_ENV\n{% endfor %}""")
        build_env = VirtualBuildEnv(self.conanfile)
        env = build_env.environment()
        envvars = env.vars(self.conanfile, scope="build")
        env_prefix = "Env:" if self.conanfile.settings.os == "Windows" else ""
        content = template.render(envvars=envvars, env_prefix=env_prefix)

        filepath = str(Path(self.conanfile.generators_folder).joinpath("activate_github_actions_buildenv"))
        if self.conanfile.settings.get_safe("os") == "Windows":
            if self.conanfile.conf.get("tools.env.virtualenv:powershell", check_type=bool):
                filepath += ".ps1"
            else:
                filepath += ".bat"
        else:
            filepath += ".sh"
        save(self.conanfile, filepath, content)
