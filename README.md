# Helipad

Helipad is an agent-based modeling framework for Python. It differs from other frameworks in that it focuses on time series output rather than spatial models.

Documentation and API reference can be found at https://helipad.dev

## How to use

You can install Helipad using Pip.

	pip install helipad

Once installed, getting started with a model is very simple. 

	from helipad import *
	heli = Helipad()
	
	#Use the heli object to set up here
	
	heli.launchGUI()

The included [bootstrap model](https://github.com/charwick/helipad/blob/master/sample-models/bootstrap.py) contains a more detailed template, and the [sample models](https://github.com/charwick/helipad/tree/master/sample-models) exemplify various use cases. The documentation also includes a complete [hook and function reference](https://helipad.dev/functions/).

## Requirements

Helipad requires Python 3.6. Previous versions do not preserve dict order, so you may get unexpected results. Python 2 is not supported.

The following libraries are required:

* [Matplotlib](https://matplotlib.org/) (for plotting the time series output)
* [Pandas](https://pandas.pydata.org/) (for data collection)

The following libraries are optional but recommended:

* [Jupyter](https://jupyter.org/) and [Ipywidgets](https://pypi.org/project/ipywidgets/) (to run Helipad in Jupyter notebooks)
    * It is recommended to run models in Jupyter Notebook rather than Jupyterlab. If you use the latter, you will also need to install the [widgets](https://ipywidgets.readthedocs.io/en/latest/user_install.html#installing-the-jupyterlab-extension) and jupyter-matplotlib extensions.
* [PMW](https://pypi.org/project/Pmw/) (for tooltips)
* [NetworkX](http://networkx.github.io/) (for network analysis)
* [Readline](https://pypi.org/project/readline/) and Code (for the debug console)
* [Pyobjc](https://pypi.org/project/pyobjc/) (for Mac interface niceties)

## Version History

* [1.1](https://helipad.dev/2020/10/helipad-1-1/): Virtual parameters, improved Jupyter flexibility, spatial pre-alpha, misc improvements
* [1.0](https://helipad.dev/2020/08/helipad-1-0/): Jupyter integration, hook decorators, and separated control panel from plotting
* [0.7](https://helipad.dev/2020/06/helipad-0-7/): Ability to output stackplots, parameter sweeps, and an updated parameter identification pattern
* [0.6](https://helipad.dev/2020/05/helipad-0-6/): Support for multi-level models
* [0.5](https://helipad.dev/2020/03/helipad-0-5/): Support for matching models, and the checkGrid class
* 0.4: Initial PyPI release