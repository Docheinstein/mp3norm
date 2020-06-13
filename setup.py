import os
import sys

from setuptools import setup, find_packages


def read(file_name):
    with open(os.path.join(os.path.dirname(__file__), file_name)) as f:
        return f.read()

print("setup.py prefix:", sys.prefix)

setup(
    name="mp3norm",
    version="0.2",

    # Requires python3.6
    python_requires=">=3.6",

    # Automatically import packages
    packages=find_packages(),

    # Include the files specified in MANIFEST.in in the release archive
    include_package_data=True,

    # Scripts to install to the user executable path.
    entry_points={
        "console_scripts": [
            "mp3norm = mp3norm.__main__:main",
        ]
    },


    # Metadata
    author="Stefano Dottore",
    author_email="docheinstein@gmail.com",
    description="Extract tags from filename and/or fetch album name/cover from Google Search",
    long_description=read('README.MD'),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="mp3norm",
    url="https://github.com/Docheinstein/mp3norm",
    install_requires=['sacad', 'eyed3', 'selenium']
)