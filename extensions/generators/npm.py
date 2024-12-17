import os
import json

from conan import ConanFile
from conan.tools.files import copy, mkdir, save
from pathlib import Path


class npm:
    def __init__(self, conanfile: ConanFile):
        self._conanfile = conanfile

    def generate(self):
        if self._conanfile.settings.os != "Emscripten":
            self._conanfile.output.error("Can only deploy to NPM when build for Emscripten")
            return

        if self._conanfile.display_name == "cli":  # We're installing a CLI package from the conan local cache
            root_package = [dep for dep in self._conanfile.dependencies.direct_host.values()][0]
            src_folder = root_package.package_folder
            conf_info = root_package.conf_info
            name = root_package.ref.name

            # Copy the *.js and *.d.ts
            copy(self._conanfile, "*.js", src=src_folder, dst=self._conanfile.generators_folder)
            copy(self._conanfile, "*.d.ts", src=src_folder, dst=self._conanfile.generators_folder)

            # Create the package.json
            save(self._conanfile, str(Path(self._conanfile.generators_folder, "package.json")),
                 json.dumps(conf_info.get(f"user.{name.lower()}:package_json")))

            # Create the .npmrc file
            save(self._conanfile, str(Path(self._conanfile.generators_folder, ".npmrc")),
                 "//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}\n@ultimaker:registry=https://npm.pkg.github.com\nalways-auth=true")
        else:  # We're generating a package for a development environment
            package_json = self._conanfile.python_requires["npmpackage"].module.generate_package_json(self._conanfile,
                os.path.join(self._conanfile.cpp.build.bindirs[0], self._conanfile.cpp.build.bin[0]))
        save(self._conanfile, str(Path(self._conanfile.build_folder, "package.json")),
             json.dumps(package_json))
