from setuptools import setup, find_packages

setup(
    name='log_center_sdk',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        "httpx>=0.24.0",
        "pydantic>=2.0.0"
    ],
)