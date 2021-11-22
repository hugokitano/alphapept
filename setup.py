import setuptools
from configparser import ConfigParser
from pkg_resources import parse_version
import os
import re
assert parse_version(setuptools.__version__) >= parse_version('36.2')

import alphapept as package2install

config = ConfigParser(delimiters=['='])
config.read('settings.ini')
cfg = config['DEFAULT']

license_options = {
    'apache2': (
        'Apache Software License 2.0',
        'OSI Approved :: Apache Software License'
    ),
    'MIT': (
        'MIT License',
        'OSI Approved :: MIT License'
    )
}
status_options = {
    '1': 'Planning',
    '2': 'Pre-Alpha',
    '3': 'Alpha',
    '4': 'Beta',
    '5': 'Production/Stable',
    '6': 'Mature',
    '7': 'Inactive'
}
maximum_python3_available = 8

with open("README.md") as readme_file:
    long_description = readme_file.read()


extra_requirements = {}
for extra, requirement_file_name in package2install.__requirements__.items():
    with open(requirement_file_name) as requirements_file:
        if extra != "":
            extra_stable = f"{extra}-stable"
        else:
            extra_stable = "stable"
        extra_requirements[extra_stable] = []
        extra_requirements[extra] = []
        for line in requirements_file:
            extra_requirements[extra_stable].append(line)
            requirement, *comparison = re.split("[><=~!]", line)
            requirement == requirement.strip()
            extra_requirements[extra].append(requirement)

requirements = extra_requirements.pop("")


def is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    from shutil import which
    return which(name) is not None
if os.name == 'posix':
    if not is_tool('mono'): #Do not try to install pythonnet if mono is not installed.
        requirements = [_ for _ in requirements if not _.startswith('pythonnet')]

setuptools.setup(
    name=cfg["lib_name"],
    license=license_options[cfg["license"]][0],
    classifiers=[
        f'Development Status :: {cfg["status"]} - {status_options[cfg["status"]]}',
        f'Intended Audience :: {cfg["audience"]}',
        f'License :: {license_options[cfg["license"]][1]}',
        f'Natural Language :: {cfg["language"]}',
    ] + [
        f'Programming Language :: Python :: 3.{i}' for i in range(
            int(cfg["min_python"].split(".")[1]),
            maximum_python3_available + 1
        )
    ],
    version=cfg["version"],
    description=cfg["description"],
    keywords=cfg["keywords"],
    author=cfg["author"],
    author_email=cfg["author_email"],
    url=cfg["url"],
    packages=setuptools.find_packages(),
    # TODO: Modifying this should allow to remove the MAINFEST.in
    include_package_data=True,
    install_requires=requirements + [
        "pywin32==225; sys_platform=='win32'"
    ],
    extras_require=extra_requirements,
    python_requires=f'>={cfg["min_python"]},<{cfg["max_python"]}',
    long_description=long_description,
    long_description_content_type='text/markdown',
    zip_safe=False,
    entry_points={
        'console_scripts': cfg.get('console_scripts', '').split()
    },
    # lib_name=cfg["lib_name"],
    # user=cfg["user"],
    # copyright=cfg["copyright"],
    # branch=cfg["branch"],
    # min_python=cfg["min_python"],
    # max_python=cfg["max_python"],
    # audience=cfg["audience"],
    # language=cfg["language"],
    # custom_sidebar=cfg["custom_sidebar"],
    # status=cfg["status"],
    # nbs_path=cfg["nbs_path"],
    # doc_path=cfg["doc_path"],
    # doc_host=cfg["doc_host"],
    # doc_baseurl=cfg["doc_baseurl"],
    # git_url=cfg["git_url"],
    # lib_path=cfg["lib_path"],
    # title=cfg["title"],
    # host=cfg["host"],
    # url_documentation=cfg["url_documentation"],
    # url_issue=cfg["url_issue"],
    # url_contribute=cfg["url_contribute"],
    # console_scripts=cfg["console_scripts"],
)
