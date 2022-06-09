import os
import shutil
import json
import sysconfig
import hashlib

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
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="xml.fdm_material" ContentType="application/x-ultimaker-material-profile" />
  <Default Extension="xml.fdm_material.sig" ContentType="application/x-ultimaker-material-sig" />
  <Default Extension="inst.cfg" ContentType="application/x-ultimaker-quality-profile" />
  <Default Extension="def.json" ContentType="application/x-ultimaker-machine-definition" />
  <Default Extension="json" ContentType="text/json" />
</Types>
"""

    _dot_rels = r"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/package.json" Type="http://schemas.ultimaker.org/package/2018/relationships/opc_metadata" Id="rel0" />
</Relationships>"""

    _package_json_rels = Template(r"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/files/{{ package_type }}s" Type="{{ package_type }}" Id="rel0" />
</Relationships>""")

    _deps_init_py = Template(r"""def initialize_paths():
    from UM.Logger import Logger
    Logger.info("Initializing the correct paths for {{ package_id }}")
    
    from pathlib import Path
    from platform import system
    from sys import path
    import sysconfig
    
    file_manifest = None
    {% if central_storage %}# Read the Central Storage manifest
    from UM.CentralFileStorage import CentralFileStorage
    import json
    central_storage_file = Path(__file__).parent.parent.joinpath("central_storage.json")
    if central_storage_file.exists():
        with open(central_storage_file, "r", encoding = "utf-8") as file_stream:
            file_manifest = json.loads(file_stream.read())
    {% endif %}
       
    # Set the base path for each dependency
    central_storage_deps = [d[1] for d in file_manifest]
    {% for dep in deps.keys() %}if file_manifest and "{{ dep }}" in central_storage_deps:
        dep_idx = central_storage_deps.index("{{ dep }}")
        {{ dep }}_base_path = Path(CentralFileStorage.retrieve(path_id = file_manifest[dep_idx][1], sha256_hash = file_manifest[dep_idx][3], version = file_manifest[dep_idx][2]))
    else:
        {{ dep }}_base_path = Path(__file__).parent.parent.joinpath("deps", r"{{ dep }}")
    {% endfor %}

    # Set the platform and python specific path
    platform_path = f"python{sysconfig.get_config_var('VERSION')}_{sysconfig.get_platform().replace('-', '_')}"

    # Set the PYTHONPATH
    {% for dep in deps.keys() %}{% if deps[dep]["pythonpaths"] | length > 0 %}{% for p in deps[dep]["pythonpaths"] %}path.append(str({{ dep }}_base_path.joinpath("site-packages", platform_path)))
    {% endfor %}{% endif %}{% endfor %}
    
    # Set the PATH
    if system() == "Windows":
        import os
    {% for dep in deps.keys() %}{% if deps[dep]["binpaths"] | length > 0 %}
    {% for p in deps[dep]["binpaths"] %}
        path_str = str({{ dep }}_base_path.joinpath(r"{{ p }}"))
        os.add_dll_directory(path_str)
        os.environ["PATH"] += f";{path_str}"
    {% endfor %}{% endif %}{% endfor %}

initialize_paths()

""")

    _package_py = Template(r"""import os
import argparse
import shutil
import sys
import zipfile

from pathlib import Path

from conans.util.files import mkdir, sha256sum

FILTERED_DIRS = ["deps", "__pycache__"]


def configure(source_dir, build_dir):
    dest_dir = Path(build_dir, "curapackage" ,r"{{ files_dir }}")
    for root, dirs, files in os.walk(os.path.normpath(source_dir)):
        root_path = Path(root)
        rel_path = root_path.relative_to(source_dir)
        if rel_path in FILTERED_DIRS or any([rel_path.is_relative_to(d) for d in FILTERED_DIRS]):
            continue

        files += [d for d in dirs if os.path.islink(os.path.join(root, d))]

        for f in files:
            src = Path(root, f)
            dst = Path(dest_dir, rel_path, f)
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


def build(build_dir, compresslevel):
    src_dir = Path(build_dir, "curapackage")
    dst_file = Path(build_dir, "{{ package_id }}-v{{ sdk_version_semver }}.curapackage")
    _compress(src_dir, dst_file, compresslevel)


def deploy(deploy_dir, compresslevel):
    src_dir = Path(deploy_dir, "curapackage/files")
    dst_file = Path(deploy_dir, "{{ package_id }}.zip")
    _compress(src_dir, dst_file, compresslevel)


def _compress(src_dir, dst_file, compresslevel):
    with zipfile.ZipFile(dst_file, "w", compression = zipfile.ZIP_LZMA, compresslevel = compresslevel) as curapackage:
        for root, dirs, files in os.walk(os.path.normpath(src_dir)):
            root_path = Path(root)
            rel_path = root_path.relative_to(src_dir)
            files += [d for d in dirs if os.path.islink(os.path.join(root, d))]

            for f in files:
                curapackage.write(root_path.joinpath(f), arcname = rel_path.joinpath(f))


def main():
    parser = argparse.ArgumentParser(description = "Create, and/or deploy a curapackage")
    parser.add_argument("--configure", action = "store_true")
    parser.add_argument("--build", action = "store_true")
    parser.add_argument("--deploy", action = "store_true")
    parser.add_argument("--compresslevel", type = int, default = 9)
    parser.add_argument("-S", type = str, default = r"{{ source_directory }}", help = "Source Path")
    parser.add_argument("-B", type = str, default = r"{{ build_directory }}", help = "Build path")
    parser.add_argument("-D", type = str, default = r"{{ build_directory }}", help = "Deploy path")
    args = parser.parse_args(sys.argv[1:])

    if not args.configure and not args.build and not args.deploy:
        parser.print_help()
        sys.exit(-1)

    if args.configure:
        configure(args.S, args.B)

    if args.build:
        build(args.B, args.compresslevel)

    if args.deploy:
        deploy(args.D, args.compresslevel)


if __name__ == "__main__":
    main()

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
        deps = {}

        central_storage = []

        for dep_name in self.conanfile.deps_cpp_info.deps:
            deps[dep_name] = {"binpaths": set(),
                              "pythonpaths": set()}
            calc_hash = dep_name in self.conanfile._curaplugin["deps"] and "central_storage" in self.conanfile._curaplugin["deps"][dep_name] and self.conanfile._curaplugin["deps"][dep_name]["central_storage"]
            hash_files = {}
            rootpath = self.conanfile.deps_cpp_info[dep_name].rootpath

            # Determine the relative paths for the binaries, used in the import deps __init__.py
            for bin_dir in self.conanfile.deps_cpp_info[dep_name].bindirs:
                bin_path = Path(bin_dir)
                if bin_path.is_absolute():
                    deps[dep_name]["binpaths"].add(Path(dep_name, bin_path.relative_to(rootpath)))
                else:
                    deps[dep_name]["binpaths"].add(Path(dep_name, bin_path))

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
                        deps[dep_name]["pythonpaths"].add(base_dst.relative_to(self._curapackage_files_path))
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
                        if calc_hash:
                            hash_files[rel_path] = sha256sum(linkto)
                    else:
                        if dst.exists():
                            src_hash = sha256sum(src)
                            if sha256sum(dst) == src_hash:
                                if calc_hash:
                                    hash_files[rel_path] = src_hash
                                continue
                        if calc_hash:
                            hash_files[rel_path] = src_hash if dst.exists() else sha256sum(src)
                        shutil.copy(src, dst)
            if calc_hash:
                sorted_hash_paths = sorted(hash_files.keys())
                hasher = hashlib.sha256()
                for hash_path in sorted_hash_paths:
                    hasher.update("".join((str(hash_path), hash_files[hash_path])).encode('utf-8'))
                dep_version = Version(self.conanfile.deps_cpp_info[dep_name].version)
                central_storage.append([os.path.join("deps", dep_name), dep_name, f"{dep_version.major}.{dep_version.minor}.{dep_version.patch}", hasher.hexdigest()])


            deps[dep_name]["binpaths"] = {bin_dir.relative_to(dep_name) for bin_dir in deps[dep_name]["binpaths"] if Path(self._curapackage_deps_path, bin_dir).exists()}

        # return the generated content
        package = self.subdict(self.conanfile._curaplugin,
                               "display_name",
                               "package_id",
                               "package_type",
                               "package_version",
                               "sdk_version",
                               "sdk_version_semver",
                               description = "package_description",
                               website = "author_website")
        package["author"] = self.subdict(self.conanfile._curaplugin,
                                         "author_id",
                                         display_name = "author_display_name",
                                         email = "author_email",
                                         website = "author_website")
        package_json = json.dumps(package, indent = 4, sort_keys = True)

        package_json_rels = self._package_json_rels.render(package_type = self.conanfile._curaplugin["package_type"])

        plugin_json = json.dumps(self.subdict(self.conanfile._curaplugin,
                                              "description",
                                              "supported_sdk_versions",
                                              version = "package_version",
                                              api = "api_version",
                                              name = "display_name",
                                              author = "author_display_name"), indent = 4, sort_keys = True)

        deps_init_py = self._deps_init_py.render(deps = deps,
                                                 central_storage = len(central_storage) > 0,
                                                 package_id = self.conanfile._curaplugin["package_id"])

        package_py = self._package_py.render(source_directory = self.conanfile.source_folder,
                                             build_directory = self.conanfile.build_folder,
                                             package_id = self.conanfile._curaplugin["package_id"],
                                             files_dir = str(self._curapackage_files_path.relative_to(self._curapackage_path)),
                                             sdk_version_semver = self.conanfile._curaplugin["sdk_version_semver"])

        content = {
            str(self._curapackage_path.joinpath("[Content_Types].xml")): self._content_types_xml,
            str(self._curapackage_path.joinpath("package.json")): package_json,
            str(self._curapackage_path.joinpath("_rels", ".rels")): self._dot_rels,
            str(self._curapackage_path.joinpath("_rels", "package.json.rels")): package_json_rels,
            str(self._curapackage_files_path.joinpath("plugin.json")): plugin_json,
            str(self._curapackage_deps_path.joinpath("__init__.py")): deps_init_py,
            str(Path(self.conanfile.generators_folder, "package.py")): package_py
        }

        if len(central_storage) > 0:
            central_storage_json = json.dumps(central_storage, indent = 4, sort_keys = True)
            content[str(self._curapackage_files_path.joinpath("central_storage.json"))] = central_storage_json

        return content