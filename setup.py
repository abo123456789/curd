from setuptools import setup, find_packages


setup(
    name='curd2',
    version='0.0.13',
    url='https://github.com/abo123456789/curd',
    description='db operations',
    author='jdxin0',
    author_email='jdxin00@gmail.com',
    license='MIT',
    keywords='db operations',
    packages=find_packages(),
    install_requires=[],
    extras_require={
        'cassandra': ['cassandra-driver==3.11.0'],
        'mysql': ['PyMySQL==0.7.11']
    }
)
