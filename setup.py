#!/usr/bin/env python3
"""Setup configuration for Rewindo."""

from pathlib import Path
from setuptools import setup, find_packages

# Get the directory containing this setup.py file
here = Path(__file__).parent

# Read README for long description
readme = here / "README.md"
long_description = readme.read_text() if readme.exists() else ""

setup(
    name="rewindo",
    version="0.1.0",
    description="Prompt-to-code timeline with one-command revert for Claude Code",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Rewindo Contributors",
    license="MIT",
    url="https://github.com/user/rewindo",
    package_dir={"": "lib"},
    packages=["rewindo"],
    entry_points={
        "console_scripts": [
            "rewindo=rewindo:main",
        ],
    },
    python_requires=">=3.9",
    install_requires=[
        # No external dependencies - uses only stdlib
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Version Control :: Git",
    ],
)
