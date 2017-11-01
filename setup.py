from setuptools import setup, find_packages

setup(
    name="EPyQ Library",
    version="0.1",
    author="EPC Power Corp.",
    classifiers=[
        ("License :: OSI Approved :: "
         "GNU General Public License v2 or later (GPLv2+)")
    ],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'collectdevices = epyqlib.collectdevices:main',
            'contiguouscommits = epyqlib.utils.contiguouscommits:_entry_point [dulwich]',
            'epyqflash = epyqlib.flash:_entry_point',
            'patchvenv = epyqlib.patchvenv:main',
            'cangenmanual = epyqlib.cangenmanual:_entry_point',
            'updateepc = epyqlib.updateepc:main',
            'genbuildinfo = epyqlib.genbuildinfo:write_build_file',
            'versionfile = epyqlib.cli.versionfile:cli',
            'generateversion = epyqlib.cli.generateversion:cli',
        ]
    },
    install_requires=[
        'gitpython',
        'graham',
        'PyQt5',
        'click',
        'python-docx',
    ],
    extras_requires={
        'deploy': [
            'gitpython',
            'requests',
        ],
        'dulwich': [
            'dulwich',
        ],
    },
)
