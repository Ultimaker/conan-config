from conan.tools.files import save

class EnvScriptBuilder:
    def __init__(self):
        self._variables = {}

    def set_variable(self, name: str, value: str):
        self._variables[name] = value

    def set_environment(self, env):
        for name, value in env.items():
            self.set_variable(name, value)

    def save(self, path, conanfile, append_to=None) -> None:
        file_path = path

        content = ""
        for name, value in self._variables.items():
            set_variable = f'{name}={value}'

            if append_to is not None:
                set_variable = f"echo {set_variable} >> {append_to}"
            else:
                set_variable = f"export {set_variable}"

            content += f"{set_variable}\n"

        if conanfile.settings.get_safe("os") == "Windows":
            if conanfile.conf.get("tools.env.virtualenv:powershell", check_type=bool):
                file_path += ".ps1"
            else:
                file_path += ".bat"
        else:
            file_path += ".sh"

        conanfile.output.info(f"Saving environment script to {file_path}")
        save(conanfile, file_path, content)
