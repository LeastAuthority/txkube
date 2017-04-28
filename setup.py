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
    url="https://github.com/LeastAuthority/txkube",
    license="MIT",
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "zope.interface",
        "attrs",
        "pyrsistent",
        "incremental",
        # See https://github.com/twisted/treq/issues/167
        # And https://twistedmatrix.com/trac/ticket/9032
        "twisted[tls]!=17.1.0",
        "pem",
        "eliot",
        "python-dateutil",
        "pykube",
        "treq",
        "klein",
    ],
    extras_require={
        "dev": [
            "testtools",
            "hypothesis",
            "eliot-tree>=17.0.0",
        ],
    },
)
