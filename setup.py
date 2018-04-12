import multiprocessing
from setuptools import setup, find_packages
setup(
    name = "forum_archive_server",
    version = "0.21",
    packages = find_packages(),

    # Dependencies on other packages:
    setup_requires   = ['nose>=1.1.2'],
    install_requires = ['pymysql_utils>=0.51'
                        ],
    tests_require    = [],

    # Unit tests; they are initiated via 'python setup.py test'
    test_suite       = 'nose.collector', 

    package_data = {
        # If any package contains *.txt or *.rst files, include them:
     #   '': ['*.txt', '*.rst'],
        # And include any *.msg files found in the 'hello' package, too:
     #   'hello': ['*.msg'],
    },

    # metadata for upload to PyPI
    author = "Andreas Paepcke",
    #author_email = "me@example.com",
    description = "Serve forum archive entries on the Web.",
    license = "BSD",
    keywords = "instruction, forum",
    url = "git@github.com:paepcke/forum_archive_server.git",   # project home page, if any
)
