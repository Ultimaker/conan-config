from pathlib import Path

from jinja2 import Template

from conan.tools.env import VirtualRunEnv
from conans.model import Generator


class PyCharmRunEnv(Generator):
    run_xml = Template(r"""<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="{{ name }}" type="PythonConfigurationType" factoryName="Python" nameIsGenerated="true">
    <module name="{{ name }}" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONUNBUFFERED" value="1" />{% for key, value in envvars.items() %}
      <env name="{{ key }}" value="{{ value }}" />{% endfor %}
    </envs>
    <option name="SDK_HOME" value="" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <option name="IS_MODULE_SDK" value="true" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <EXTENSION ID="PythonCoverageRunConfigurationExtension" runner="coverage.py" />
    <option name="SCRIPT_NAME" value="$PROJECT_DIR$/{{ entrypoint }}" />
    <option name="PARAMETERS" value="" />
    <option name="SHOW_COMMAND_LINE" value="false" />
    <option name="EMULATE_TERMINAL" value="false" />
    <option name="MODULE_MODE" value="false" />
    <option name="REDIRECT_INPUT" value="false" />
    <option name="INPUT_FILE" value="" />
    <method v="2" />
  </configuration>
</component>    """)

    @property
    def filename(self):
        stem = Path(self.conanfile._um_data(self.conanfile.version)["runinfo"]["entrypoint"]).stem
        return str(Path(self.conanfile.source_folder).joinpath(".run", f"{stem}.run.xml"))

    @property
    def content(self):
        run_env = VirtualRunEnv(self.conanfile)
        env = run_env.environment()
        envvars = env.vars(self.conanfile, scope = "run")
        return self.run_xml.render(name = self.conanfile.name, envvars = envvars,
                                   entrypoint = self.conanfile._conan_data["runinfo"]["entrypoint"])
