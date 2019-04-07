# Copyright (c) 2019 John L. Villalovos

from __future__ import print_function

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="hardlinkpy",
    version="0.06.1",
    author="John L. Villalovos",
    author_email="john@sodarock.com",
    description="A program to hardlink identical files together",
    entry_points={
        "console_scripts": [
            "hardlinkpy=hardlinkpy.hardlink:main",
            "hardlink.py=hardlinkpy.hardlink:main",
        ]
    },
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/JohnVillalovos/hardlinkpy",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPL v2",
        "Operating System :: Linux",
    ],
)
