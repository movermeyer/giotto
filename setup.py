from setuptools import setup

setup(
    name='giotto',
    version='0.9.18',
    description='Python web development simplified',
    long_description=open('README.rst').read(),
    author='Chris Priest',
    author_email='cp368202@ohiou.edu',
    url='https://github.com/priestc/giotto',
    packages=[
        'giotto',
        'giotto.controllers',
        'giotto.programs',
        'giotto.contrib',
        'giotto.contrib.auth',
        'giotto.contrib.static',
        'giotto.views'
    ],
    scripts=['bin/giotto'],
    include_package_data=True,
    license='LICENSE',
    install_requires=[
        'webob==1.2.3',
        'irc==5.0.1',
        'jinja2==2.6',
        'py-bcrypt==0.2',
        'mimeparse==0.1.3',
        'sqlalchemy==0.7.9',
    ],
)