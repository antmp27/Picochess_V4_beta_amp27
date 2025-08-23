#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="picochess",
    version="4.0.0",
    author="Johan Sjöblom",
    author_email="",
    description="Chess computer for Raspberry Pi and Debian systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/antmp27/picochess-keyboard",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Games/Entertainment :: Board Games",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "picochess=picochess:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.ini", "*.txt", "*.md", "*.bin", "*.uci"],
    },
)