from pathlib import Path

from conan import ConanFile
from conan.tools.env import VirtualRunEnv

from EnvScriptBuilder import EnvScriptBuilder


class GitHubActionsRunEnv:
    def __init__(self, conanfile: ConanFile):
        self.conanfile: ConanFile = conanfile

    def generate(self):
        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()
        envvars = env.vars(self.conanfile, scope="run")
        env_prefix = "Env:" if self.conanfile.settings.os == "Windows" else ""
        filepath = str(Path(self.conanfile.generators_folder).joinpath("activate_github_actions_runenv"))

        script_builder = EnvScriptBuilder()
        script_builder.set_environment(envvars)
        script_builder.save(filepath, self.conanfile, f"${env_prefix}GITHUB_ENV")
