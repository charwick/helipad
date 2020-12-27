# A template for bootstrapping new models.
# See https://helipad.dev/ for complete documentation

#===============
# SETUP
# Instantiate the object and add parameters, breeds, and goods below.
#===============

from helipad import Helipad
# from utility import CobbDouglas

heli = Helipad()
heli.name = 'Model Name'
heli.order = 'random' #Can be changed to 'linear' or 'match'
heli.stages = 1 #Change to create a multi-stage model

# heli.addParameter('name', 'title', 'type (slider, menu, or check)', dflt=default, opts={depends on type})
# heli.addGood('good1','hex color', lambda breed: endowment)
# heli.addBreed('name1', 'hex color')
# heli.addBreed('name2', 'hex color')

#===============
# BEHAVIOR
# A list of hooks and their function signatures can be found at http://helipad-docs.nfshost.com/hooks/
#===============

#Any variables or properties the agent should keep track of should have default values set here.
@heli.hook
def agentInit(agent, model):
	#agent.myAgentProperty = 0
	#agent.utility = CobbDouglas(['good1'])
	pass

#Any global variables that should be kept track of should have default values set here.
@heli.hook
def modelPostSetup(model):
	#model.myModelProperty = 0
	pass

#Agent logic should be written here.
@heli.hook
def agentStep(agent, model, stage):
	pass	

#Any global code to be run each period should be hooked to modelStep, modelPreStep, or modelPostStep.
#modelStep will run as many times per period as there are stages. modelPreStep and modelPostStep
#will run at the beginning and end of each period, respectively, and do not take a stage argument.
@heli.hook
def modelStep(model, stage):
	pass

#===============
# DATA AND VISUALIZATION
# Register reporters, plots, and series here
#===============

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)

#Reporters collect data from the model each period, generally from parameters set in agentInit and modelPostSetup.

# heli.data.addReporter('myReporter1', heli.data.agentReporter('myAgentProperty', 'agent', stat='mean'))
# heli.data.addReporter('myReporter2', heli.data.modelReporter('myModelProperty'))

#Plots are areas on the graph where series can be drawn to keep track of reporter data in real time.

myplot = viz.addPlot('myplot', 'Custom Properties', logscale=False, selected=True)

#Series draw reporter data on a plot. Here we draw two series on the same plot.
#The Plot object can also be accessed later with heli.plots['myplot'], so the following two methods are identical.

# myplot.addSeries('myplot', 'myReporter1', 'My Agent Property', 'hex color')
# heli.plots['myplot'].addSeries('myplot', 'myReporter2', 'My Model Property', 'hex color')

#===============
# LAUNCH THE GUI
#===============

heli.launchCpanel()