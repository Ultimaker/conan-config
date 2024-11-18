from pathlib import Path

from conan import ConanFile
from conan.tools.env import VirtualBuildEnv

from EnvScriptBuilder import EnvScriptBuilder


class GitHubActionsBuildEnv:
    def __init__(self, conanfile: ConanFile):
        self.conanfile: ConanFile = conanfile

    def generate(self):
        build_env = VirtualBuildEnv(self.conanfile)
        env = build_env.environment()
        envvars = env.vars(self.conanfile, scope="build")
        env_prefix = "Env:" if self.conanfile.settings.os == "Windows" else ""
        filepath = str(Path(self.conanfile.generators_folder).joinpath("activate_github_actions_buildenv"))

        script_builder = EnvScriptBuilder()
        script_builder.set_environment(envvars)
        script_builder.save(filepath, self.conanfile, f"${env_prefix}GITHUB_ENV")
