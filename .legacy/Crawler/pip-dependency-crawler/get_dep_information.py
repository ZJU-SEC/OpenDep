import requests
import tempfile
import os
import rarfile
import tarfile
import zipfile
from packaging.utils import canonicalize_name
from .setup_parse_dep import DepsVisitor
import configparser
import toml
from pip._internal.models.wheel import Wheel
from pkginfo import Wheel as Wheel_pkginfo, SDist as SDist_pkginfo, BDist as BDist_pkginfo
from pkg_resources import split_sections
from wheel.metadata import generate_requirements

# Get archive contents
def _get_archive(fqn):
    if not os.path.exists(fqn):
        raise ValueError(f'No such file: {fqn}')

    if zipfile.is_zipfile(fqn):
        archive = zipfile.ZipFile(fqn)
        names = archive.namelist()

        def read_file(name):
            return archive.read(name)

        def extract_file(path):
            return archive.extractall(path=path)

    elif tarfile.is_tarfile(fqn):
        archive = tarfile.TarFile.open(fqn)
        names = archive.getnames()

        def read_file(name):
            return archive.extractfile(name).read()

        def extract_file(path):
            return archive.extractall(path=path)

    elif rarfile.is_rarfile(fqn):
        archive = rarfile.RarFile(fqn)
        names = archive.namelist()

        def read_file(name):
            return archive.read(name)

        def extract_file(path):
            return archive.extractall(path=path)

    else:
        raise ValueError(f'Not a known archive format: {fqn}')

    return archive, names, read_file, extract_file

# Parse setup.py
def parse_setup_file(setup_file_path):
    try:
        ast_parse_setup = DepsVisitor(setup_file_path)
        dependencies = ast_parse_setup.end_dataflow
        alldeps = []
        for key in dependencies:
            if key.from_ == "install_requires":
                alldeps.append(key.to_)
            if key.from_ == "extras_require":
                alldeps.append(f"{key.to_} ; extra == '{key.extra_info.value}'")
        return alldeps
    except:
        return []

# Parse setup.cfg
def parse_setup_cfg_file(setupcfg_file_path):
    with open(setupcfg_file_path, "r") as f:
        setup_cfg = f.read()
    alldeps = []
    config = configparser.ConfigParser()
    config.read_string(setup_cfg)

    if 'options' in config:
        if 'install_requires' in config['options']:
            alldeps.extend(config['options']['install_requires'].strip().split("\n"))

        if 'extras_require' in config['options']:
            for key, value in config['options']['extras_require'].items():
                alldeps.extend([f"{dep} ; extra == '{key}'" for dep in (value if isinstance(value, list) else [value])])

    return alldeps

# Parse pyproject.toml
def parse_pyproject_toml_file(pyproject_toml_file_path):
    alldeps = []
    with open(pyproject_toml_file_path, "r") as f:
        pyproject_toml = f.read()

    config = toml.loads(pyproject_toml)
    if 'project' in config:
        if 'dependencies' in config['project']:
            alldeps.extend(config['project']['dependencies'])
        if 'optional-dependencies' in config['project']:
            for key, value in config['project']['optional-dependencies'].items():
                alldeps.extend([f"{dep} ; extra == '{key}'" for dep in (value if isinstance(value, list) else [value])])

    elif 'tool' in config and 'poetry' in config['tool']:
        poetry_config = config['tool']['poetry']
        for key, value in poetry_config.get('dependencies', {}).items():
            if key == 'python':
                continue
            dep = f"{key}{value.replace('^', '~=').replace('*', '')}" if isinstance(value, str) else key
            alldeps.append(dep)
        if 'extras' in poetry_config:
            for extra_key, extra_value in poetry_config['extras'].items():
                alldeps.extend([f"{dep} ; extra == '{extra_key}'" for dep in extra_value])

    return alldeps

# Parse requirements.txt
def parse_requirements_txt_file(requirements_txt_file_path):
    alldeps = []
    with open(requirements_txt_file_path, "r") as f:
        requirements_txt = f.readlines()
        for req in requirements_txt:
            if req.startswith("#"):
                continue
            alldeps.append(req.split("# ")[0].strip())
    return alldeps

# Get dependencies from package
def get_dep_information_from_package(file_path):
    if not file_path.endswith((".zip", ".tar.gz", ".whl", ".egg")):
        raise Exception(f"Unsupported file type: {file_path}")

    file_name = os.path.basename(file_path)
    new_file_name = next((file_name[:-len(ext)] for ext in [".whl", ".tar.gz", ".egg", ".zip"] if file_name.endswith(ext)), None)

    if file_path.endswith(".whl"):
        meta = Wheel(file_name)
        file_package_name, file_package_version = meta.name, meta.version
    else:
        file_package_version = new_file_name.split("-")[-1]
        file_package_name = new_file_name[:-len(file_package_version)-1]

    archive, names, read_file, extract_file = _get_archive(file_path)
    alldeps = []

    if file_name.endswith((".whl", ".egg")):
        pkgmetadata = Wheel_pkginfo(file_path) if file_name.endswith(".whl") else BDist_pkginfo(file_path)
        if pkgmetadata.requires_dist:
            return list(pkgmetadata.requires_dist)

        for name in names:
            if name.endswith("requires.txt"):
                requires = read_file(name).decode("utf-8").strip()
                parsed_requirements = sorted(split_sections(requires), key=lambda x: x[0] or "")
                for extra, reqs in parsed_requirements:
                    alldeps.extend(value for key, value in generate_requirements({extra: reqs}) if key == 'Requires-Dist')
                return alldeps

    elif file_name.endswith((".zip", ".tar.gz")):
        for name in names:
            if name.endswith(f"{file_package_name.replace('-', '_')}.egg-info/requires.txt"):
                requires = read_file(name).decode("utf-8").strip()
                parsed_requirements = sorted(split_sections(requires), key=lambda x: x[0] or "")
                alldeps.extend(value for key, value in generate_requirements({extra: reqs}) if key == 'Requires-Dist')
                return alldeps

            if name.endswith(f"{file_package_name}-{file_package_version}/setup.py"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    setup_file_path = os.path.join(temp_dir, "setup.py")
                    with open(setup_file_path, "wb") as f:
                        f.write(read_file(name))
                    alldeps.extend(parse_setup_file(setup_file_path))

            elif name.endswith(f"{file_package_name}-{file_package_version}/setup.cfg"):
                alldeps.extend(parse_setup_cfg_file(read_file(name).decode("utf-8", errors="ignore")))

            elif name.endswith(f"{file_package_name}-{file_package_version}/pyproject.toml"):
                alldeps.extend(parse_pyproject_toml_file(read_file(name).decode("utf-8", errors="ignore")))

        return alldeps
    else:
        print(f"Unsupported file type: {file_name}")
        return
