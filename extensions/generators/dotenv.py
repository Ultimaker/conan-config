import os
from conan.tools.env import VirtualRunEnv
from conan.tools.files import copy, save, load

class dotenv:

    def __init__(self, conanfile):
        self._conanfile = conanfile

    def generate(self):
        run_env = VirtualRunEnv(self._conanfile)
        env = run_env.environment()
        env_vars = env.vars(self._conanfile, scope="run")
        output_file = ".env"
        self._conanfile.output.info(f"Generating '{output_file}' with run environment variables...")

        content = ""
        for key, value in env_vars.items():
            content += f"{key}={value}\n"
        self._conanfile.output.info(f"'{output_file}' generated successfully.")
        save(self._conanfile, output_file, content)
        self._conanfile.output.info(f"Saved '{output_file}' to the current directory.")
