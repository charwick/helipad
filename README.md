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

* Colour (for the user interface)
* Matplotlib (for plotting the time series output)
* Pandas (for data collection)

The following libraries are optional but recommended:

* PMW (for tooltips)
* NetworkX (for network analysis)
* Readline and Code (for the debug console)
* Pyobjc (for Mac interface niceties)

## Version History

* 0.7: Ability to output stackplots, parameter sweeps, and an updated parameter identification pattern
* 0.6: Support for multi-level models
* 0.5: Support for matching models, and the checkGrid class
* 0.4: Initial PyPI release