import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="helipad",
    version="0.2",
    author="C Harwick",
    author_email="cameron@cameronharwick.com",
    description="A time-series focused agent-based modeling framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/charwick/helipad",
    packages=setuptools.find_packages(),
	license='MIT',
	install_requires=[
		'colour',
		'matplotlib',
		'pandas'
	],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)