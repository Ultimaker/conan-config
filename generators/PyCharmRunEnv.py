from pathlib import Path

from jinja2 import Template

from conans import tools
from conan.tools.env import VirtualRunEnv
from conans.model import Generator


class PyCharmRunEnv(Generator):
    run_xml = Template(r"""<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="{{ name }}" type="PythonConfigurationType" factoryName="Python" nameIsGenerated="true">
    <module name="{{ module_name }}" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONUNBUFFERED" value="1" />{% for key, value in envvars.items() %}
      <env name="{{ key }}" value="{{ value }}" />{% endfor %}
    </envs>
    <option name="SDK_HOME" value="{{ sdk_path }}" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <option name="IS_MODULE_SDK" value="true" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <EXTENSION ID="PythonCoverageRunConfigurationExtension" runner="coverage.py" />
    <option name="SCRIPT_NAME" value="$PROJECT_DIR$/{{ script_name }}" />
    <option name="PARAMETERS" value="{{ parameters }}" />
    <option name="SHOW_COMMAND_LINE" value="false" />
    <option name="EMULATE_TERMINAL" value="false" />
    <option name="MODULE_MODE" value="false" />
    <option name="REDIRECT_INPUT" value="false" />
    <option name="INPUT_FILE" value="" />
    <method v="2" />
  </configuration>
</component>    """)

    @property
    def _base_dir(self):
        return Path("$PROJECT_DIR$", "venv")

    @property
    def _py_interp(self):
        if self.settings.os == "Windows":
            py_interp = Path(*[f'"{p}"' if " " in p else p for p in self._base_dir.joinpath("Scripts", "python.exe").parts])
            return py_interp
        return self._base_dir.joinpath("bin", "python")

    @property
    def _site_packages(self):
        if self.settings.os == "Windows":
            return self._base_dir.joinpath("Lib", "site-packages")
        py_version = tools.Version(self.conanfile.deps_cpp_info["cpython"].version)
        return self._base_dir.joinpath("lib", f"python{py_version.major}.{py_version.minor}", "site-packages")

    @property
    def filename(self):
        pass

    @property
    def content(self):
        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()
        env.prepend_path("PYTHONPATH", str(self._site_packages))

        if hasattr(self.conanfile, f"_{self.conanfile.name}_run_env"):
            project_run_env = getattr(self.conanfile, f"_{self.conanfile.name}_run_env")
            if project_run_env:
                env.compose_env(project_run_env)  # TODO: Add logic for dependencies

        envvars = env.vars(self.conanfile, scope = "run")

        pycharm_targets = {}
        if hasattr(self.conanfile, "_pycharm_targets"):
            for target in self.conanfile._pycharm_targets:
                kwarg = target
                kwarg["envvars"] = envvars
                kwarg["sdk_path"] = str(self._py_interp)
                if "parameters" not in kwarg:
                    kwarg["parameters"] = ""

                pycharm_targets[str(Path(self.conanfile.source_folder).joinpath(".run", f"{kwarg['name']}.run.xml"))] = self.run_xml.render(**kwarg)

        return pycharm_targets
