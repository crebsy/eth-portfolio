from setuptools import find_packages, setup # type: ignore
import re

with open("requirements.txt", "r") as f:
    requirements = []
    for line in f.read().split("\n"):
        m = re.match("git\+https://www.github.com/[^/]+/([^/]+)@[^/]+", line)
        if m:
            requirements.append(f"{m[1]} @ {line.strip()}")
        else:
            requirements.append(line.strip())

setup(
    name='eth-portfolio',
    packages=find_packages(),
    use_scm_version={
        "root": ".",
        "relative_to": __file__,
        "local_scheme": "no-local-version",
        "version_scheme": "python-simplified-semver",
    },
    description='eth-portfolio makes it easy to analyze your portfolio.',
    author='BobTheBuidler',
    author_email='bobthebuidlerdefi@gmail.com',
    url='https://github.com/BobTheBuidler/eth-portfolio',
    install_requires=requirements,
    setup_requires=[
        'setuptools_scm',
    ],
    package_data={
        "eth_portfolio": ["py.typed"],
    },
)
