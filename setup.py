#!/usr/bin/env python

# Copyright Least Authority Enterprises.
# See LICENSE for details.

import setuptools

_metadata = {}
with open("src/txkube/_metadata.py") as f:
    exec(f.read(), _metadata)

setuptools.setup(
    name="txkube",
    version=_metadata["version_string"],
    description="A Twisted-based Kubernetes client.",
    author="txkube Developers",
    url="https://github.com/leastauthority.com/txkube",
    license="MIT",
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    install_requires=[
        "zope.interface",
        "attr",
        "pyrsistent",
        "incremental",
        "twisted[tls]",
        "eliot",
    ],
    extras_require={
        "dev": [
            "treq",
            "pem",
            "pyyaml",
            "testtools",
            "hypothesis",
            "eliot",
            "eliot-tree",
        ],
    },
)
