"""This module contains the packaging routine for the pybook package"""

from setuptools import setup, find_packages

def get_requirements(source):
    with open(source) as f:
        requirements = f.read().splitlines()

    required = []
    dependency_links = []
    # do not add to required lines pointing to git repositories
    EGG_MARK = '#egg='
    for line in requirements:
        if line.startswith('-e git:') or line.startswith('-e git+') or \
                line.startswith('git:') or line.startswith('git+'):
            if EGG_MARK in line:
                package_name = line[line.find(EGG_MARK) + len(EGG_MARK):]
                required.append(package_name)
                dependency_links.append(line)
            else:
                print('Dependency to a git repository should have the format:')
                print('git+ssh://git@github.com/xxxxx/xxxxxx#egg=package_name')
        else:
            required.append(line)

    return required

setup(
    packages=find_packages(),
    install_requires=get_requirements('requirements/requirements.txt')
)
