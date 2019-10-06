from distutils.core import setup

from setuptools import find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

pkg_name = 'ganglion-biosensing'
version = '0.1.2'

setup(
    name=pkg_name,
    packages=find_packages(exclude='examples'),
    version=version,
    license='MIT',
    description='Modern Python 3.7+ library for interfacing with the OpenBCI '
                'Ganglion biosensing board over BTLE.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    author='Manuel Olguin Munoz',
    author_email='manuel@olguin.se',
    url=f'https://github.com/molguin92/{pkg_name}',
    download_url=f'https://github.com/molguin92/'
                 f'{pkg_name}/archive/{version}.tar.gz',
    keywords=['device', 'control', 'eeg', 'emg', 'ekg', 'ads1299', 'openbci',
              'ganglion'],
    install_requires=['numpy', 'bitstring', 'bluepy'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
)
