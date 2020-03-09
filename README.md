# Helipad

Helipad is an agent-based modeling framework for Python. It differs from other frameworks in that it focuses on time series output rather than spatial models.

Documentation is a work in progress, and can be found at https://helipad.dev

## How to use

	from model import Helipad
	heli = Helipad()
	
	#Use the heli object to set up here
	
	heli.launchGUI()

A bootstrap model is included to get started. See the documentation for more usage details.

## Requirements

Helipad requires Python 3.6. Previous versions do not preserve dict order, so you may get unexpected results. Python 2 is not supported.

The following libraries are required:

* Colour (for the user interface)
* Matplotlib (for plotting the time series output)
* Pandas (for data collection)

The following libraries are optional but recommended:

* Readline (for the debug console)
* Code (for the debug console)
* PMW (for tooltips)
* NetworkX (for network analysis)
* Pyobjc (for Mac interface niceties)

## Version History

* 0.4: Basic graph and network functionality
* 0.3: Improvements to goods API
* 0.2: Abstraction of agent-type primitives
* 0.1: Initial release