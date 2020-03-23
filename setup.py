import setuptools

with open("README.md", "r") as fh:
	long_description = fh.read()

setuptools.setup(
	name="helipad",
	version="0.4.2",
	author="C Harwick",
	author_email="cameron@cameronharwick.com",
	description="An agent-based modeling framework for Python focused on time-series output.",
	long_description=long_description,
	long_description_content_type="text/markdown",
	url="https://helipad.dev",
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
		"Development Status :: 4 - Beta",
		"Intended Audience :: Science/Research",
		"Topic :: Scientific/Engineering :: Visualization"
	],
	python_requires='>=3.6',
)