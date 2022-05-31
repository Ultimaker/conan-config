import os
import shutil
import json
import sysconfig

from pathlib import Path

from jinja2 import Template

from conans.errors import ConanInvalidConfiguration
from conans.model import Generator
from conans.util.files import mkdir, sha256sum
from conans.tools import Version

FILTERED_FILES = ["conaninfo.txt", "conanmanifest.txt"]
FILTERED_DIRS = ["include"]


class CuraPackage(Generator):
    _content_types_xml = r"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default ContentType="application/vnd.openxmlformats-package.relationships+xml" Extension="rels" />
  <Default ContentType="application/x-ultimaker-material-profile" Extension="xml.fdm_material" />
  <Default ContentType="application/x-ultimaker-material-sig" Extension="xml.fdm_material.sig" />
  <Default ContentType="application/x-ultimaker-quality-profile" Extension="inst.cfg" />
  <Default ContentType="application/x-ultimaker-machine-definition" Extension="def.json" />
  <Default ContentType="text/json" Extension="json" />
</Types>"""

    _dot_rels = r"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/package.json" Type="http://schemas.ultimaker.org/package/2018/relationships/opc_metadata" Id="rel0" />
</Relationships>"""

    _package_json_rels = r"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/plugins" Type="plugin" Id="rel0" />
</Relationships>"""

    _deps_init_py = Template(r"""def initialize_paths():
    {% if py_deps | length > 0 or bin_deps | length > 0 %}from pathlib import Path
    {% if bin_deps | length > 0 %}from platform import system{% endif %}
    {% if py_deps | length > 0 %}from sys import path
    import sysconfig

    platform_path = f"python{sysconfig.get_config_var('VERSION')}_{sysconfig.get_platform().replace('-', '_')}"{% endif %}  
    {% if py_deps | length > 0 %}{% for dep in py_deps %}path.append(str(Path(__file__).parent.parent.joinpath(r"{{ dep }}", platform_path))){% endfor %}{% endif %}

    {% if bin_deps | length > 0 %}if system() == "Windows":
        from os import add_dll_directory
        {% for dep in bin_deps %}add_dll_directory(str(Path(__file__).parent.joinpath(r"{{ dep }}")))
        {% endfor %}{% endif %}{%  else %}pass{% endif %}

initialize_paths()

""")

    def subdict(self, base, *keys, **kwargs):
        sub = dict(zip(keys, [base[k] for k in keys]))
        for k, v in kwargs.items():
            sub[k] = base[v]
        return sub

    @property
    def _curapackage_path(self):
        return Path(self.conanfile.build_folder, "curapackage")

    @property
    def _curapackage_files_path(self):
        return Path(self._curapackage_path,
                    "files",
                    f"{self.conanfile._curaplugin['package_type']}s",
                    self.conanfile._curaplugin['package_id'],
                    self.conanfile._curaplugin['package_id'])

    @property
    def _curapackage_deps_path(self):
        return Path(self._curapackage_files_path, "deps")

    @property
    def filename(self):
        pass

    @property
    def content(self):
        if not hasattr(self.conanfile, "_curaplugin"):
            raise ConanInvalidConfiguration()

        #  Copy dependencies
        site_packages = set()
        bin_dirs = set()

        for dep_name in self.conanfile.deps_cpp_info.deps:
            rootpath = self.conanfile.deps_cpp_info[dep_name].rootpath

            # Determine the relative paths for the binaries, used in the import deps __init__.py
            for bin_dir in self.conanfile.deps_cpp_info[dep_name].bindirs:
                bin_path = Path(bin_dir)
                if bin_path.is_absolute():
                    bin_dirs.add(Path(dep_name, bin_path.relative_to(rootpath)))
                else:
                    bin_dirs.add(Path(dep_name, bin_path))

            # Copy/link the files
            for root, dirs, files in os.walk(os.path.normpath(rootpath)):
                files += [d for d in dirs if os.path.islink(os.path.join(root, d))]
                rel_path = Path(os.path.relpath(root, rootpath))
                if rel_path in FILTERED_DIRS or any([rel_path.is_relative_to(d) for d in FILTERED_DIRS]):
                    continue

                for f in files:
                    if f in FILTERED_FILES:
                        continue

                    src = Path(os.path.normpath(os.path.join(root, f)))
                    if rel_path == Path("site-packages"):
                        py_version = Version(self.conanfile.options.python_version)
                        # FIXME: for different architectures and OSes
                        base_dst = Path(self._curapackage_deps_path, dep_name, os.path.relpath(root, rootpath))
                        site_packages.add(base_dst.relative_to(self._curapackage_files_path))
                        dst = os.path.join(base_dst,
                                           f"python{py_version.major}{py_version.minor}_{sysconfig.get_platform().replace('-', '_')}", f)
                    else:
                        dst = os.path.join(self._curapackage_deps_path, dep_name, os.path.relpath(root, rootpath), f)
                    dst = Path(os.path.normpath(dst))
                    mkdir(os.path.dirname(dst))
                    if os.path.islink(src):
                        link_target = os.readlink(src)
                        if not os.path.isabs(link_target):
                            link_target = os.path.join(os.path.dirname(src), link_target)
                        linkto = os.path.relpath(link_target, os.path.dirname(src))
                        if os.path.isfile(dst) or os.path.islink(dst):
                            os.unlink(dst)
                        os.symlink(linkto, dst)
                    else:
                        if dst.exists():
                            if sha256sum(dst) == sha256sum(src):
                                continue
                        shutil.copy(src, dst)

        bin_dirs = {bin_dir for bin_dir in bin_dirs if Path(self._curapackage_deps_path, bin_dir).exists()}

        # return the generated content
        package = self.subdict(self.conanfile._curaplugin,
                               "description",
                               "display_name",
                               "package_id",
                               "package_type",
                               "package_version",
                               "sdk_version",
                               "sdk_version_semver",
                               "author_website")
        package["author"] = self.subdict(self.conanfile._curaplugin,
                                         "author_id",
                                         display_name = "author_display_name",
                                         email = "author_email",
                                         website = "author_website"
                                         )
        package_json = json.dumps(package)
        plugin_json = json.dumps(self.subdict(self.conanfile._curaplugin,
                                              "display_name",
                                              "author_display_name",
                                              "package_version",
                                              "description",
                                              "api_version",
                                              "supported_sdk_versions"))

        deps_init_py = self._deps_init_py.render(py_deps = site_packages, bin_deps = bin_dirs)

        return {
            str(Path(self._curapackage_path, "[Content_Types].xml")): self._content_types_xml,
            str(Path(self._curapackage_path, "package.json")): package_json,
            str(Path(self._curapackage_path, "_rels", ".rels")): self._dot_rels,
            str(Path(self._curapackage_path, "_rels", "package.json.rels")): self._package_json_rels,
            str(Path(self._curapackage_files_path, "plugin.json")): plugin_json,
            str(Path(self._curapackage_deps_path, "__init__.py")): deps_init_py
        }
