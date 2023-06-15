# Helipad

Helipad is an agent-based modeling framework for Python with powerful visualization capabilities and a shallow learning curve. Documentation and API reference can be found at [helipad.dev](https://helipad.dev).

## Features

* ⚓️ A simple [hook-based API](https://helipad.dev/glossary/hooks/) makes it easy to build a model without worrying about the features you don’t need
* 📈 Interactive and live-updating visualizations, including time series, bar charts, networks, spatial, and an API for writing custom visualizations
* 👋🏻 Flexible parameter API allows parameter values to be set programmatically, adjusted manually from the control panel while the model is running, or shocked stochastically
* 🪐 Cross-platform and multimodal. Models can be written and run with a Tkinter GUI, in Jupyter notebooks, or without a GUI at all
* 🤹🏻‍♂️ Agents can barter, buy and sell with money, reproduce both haploid and polyploid, and more
* 🕺🏻 A variety of model types: sequential or random-activation models, matching models, multi-level models, network models, spatial models, and more

## How to Use

You can install Helipad using either Pip or Conda, depending on your preferred package manager.

	pip install helipad
 
	conda install -c charwick helipad

Once installed, getting started with a model is very simple. 

	from helipad import *
	heli = Helipad()
	
	#Use the heli object to set up here
	
	heli.launchCpanel()

The included [bootstrap model](https://github.com/charwick/helipad/blob/master/sample-models/bootstrap.py) contains a more detailed template, and the [sample models](https://github.com/charwick/helipad/tree/master/sample-models) exemplify various use cases. The documentation also includes a complete [hook and function reference](https://helipad.dev/functions/).

## Requirements

Helipad requires Python 3.8 or higher. The following libraries are also required:

* [Matplotlib](https://matplotlib.org/) for visualization
* [Pandas](https://pandas.pydata.org/) for data collection
* [NetworkX](http://networkx.github.io/) for network analysis and spatial visualization
* _Optional:_ [Jupyter](https://jupyter.org/), [Ipywidgets](https://pypi.org/project/ipywidgets/), and [ipympl](https://github.com/matplotlib/ipympl) to run Helipad in Jupyter notebooks
* _Optional:_ [Shapely](https://shapely.readthedocs.io/) for geospatial models.

## How to Cite

If you use Helipad in your own research, please cite as follows:

> Harwick, Cameron (2021). “Helipad: A Framework for Agent-Based Modeling in Python.” Working paper available at [ssrn.com/abstract=3870501](https://ssrn.com/abstract=3870501). 

## Version History

* [1.6](https://helipad.dev/2023/06/helipad-1-6/): Geospatial models, agent scatterplot visualizer, new `Agents` and `Edges` containers
* [1.5](https://helipad.dev/2023/01/helipad-1-5/): Polar grid spatial models, various spatial improvements
* [1.4](https://helipad.dev/2022/07/helipad-1-4/): More consistent container API, localization, miscellaneous interface improvements
* [1.3](https://helipad.dev/2021/06/helipad-1-3/): Allow mixing time series and other plots, display networks on spatial maps, goods API improvements
* [1.2](https://helipad.dev/2021/02/helipad-1-2/): Extensible visualization API, events, performance profiling, Jupyterlab support
* [1.1](https://helipad.dev/2020/10/helipad-1-1/): Virtual parameters, improved Jupyter flexibility, spatial pre-alpha, misc improvements
* [1.0](https://helipad.dev/2020/08/helipad-1-0/): Jupyter integration, hook decorators, and separated control panel from plotting
* [0.7](https://helipad.dev/2020/06/helipad-0-7/): Ability to output stackplots, parameter sweeps, and an updated parameter identification pattern
* [0.6](https://helipad.dev/2020/05/helipad-0-6/): Support for multi-level models
* [0.5](https://helipad.dev/2020/03/helipad-0-5/): Support for matching models, and the `checkGrid` class
* 0.4: Initial PyPI release