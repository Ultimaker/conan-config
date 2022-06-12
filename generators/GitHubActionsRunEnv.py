from pathlib import Path

from jinja2 import Template

from conan.tools.env import VirtualRunEnv
from conans.model import Generator


class GitHubActionsRunEnv(Generator):

    @property
    def filename(self):
        filepath = str(Path(self.conanfile.generators_folder).joinpath("activate_github_actions_runenv"))
        if self.conanfile.settings.get_safe("os") == "Windows":
            if self.conanfile.conf.get("tools.env.virtualenv:powershell", check_type = bool):
                filepath += ".ps1"
            else:
                filepath += ".bat"
        else:
            filepath += ".sh"
        return filepath

    @property
    def content(self):
        template = Template("""{% for k, v in envvars.items() %}echo "{{ k }}={{ v }}" >> $GITHUB_ENV\n{% endfor %}""")
        build_env = VirtualRunEnv(self.conanfile)
        env = build_env.environment()
        envvars = env.vars(self.conanfile, scope = "run")
        return template.render(envvars = envvars)
