# Helipad

Helipad is an agent-based modeling framework for Python. It differs from other frameworks in that it focuses on time series output rather than spatial models.

Documentation is a work in progress, and can be found at http://helipad-docs.nfshost.com/

## How to use

	from model import Helipad
	heli = Helipad()
	
	#Use the heli object to set up here
	
	heli.launchGUI()

See the documentation and the included sample models for more usage details.

## Requirements

Helipad requires Python 3.6. Previous versions do not preserve dict order, so you may get unexpected results. Python 2 is not supported.

The following libraries are required:

* Tkinter (for the user interface)
* Colour (for the user interface)
* Matplotlib (for plotting the time series output)
* Pandas (for data collection)

The following libraries are optional but recommended:

* Readline (for the debug console)
* Code (for the debug console)
* Pyobjc (for Mac interface niceties)

## Version History

* 0.1: Initial release