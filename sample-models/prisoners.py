# An experiment to verify the logic in https://www.youtube.com/watch?v=iSNsgj1OCLA
# 100 prisoners, each with a number, enters a room with 100 numbered boxes, each with a
# random number inside. Each may open only 50 boxes. If everyone finds their own number,
# they are all freed. If anyone fails to find their number, they are all executed. There
# is no communication once the game starts. Can they do better than 0.5**100 chance?
# This model verifies that indeed they can.

#===============
# SETUP
#===============

from random import shuffle, randint
from helipad import Helipad
from numpy import mean

heli = Helipad()
heli.name = 'Prison Escape'
heli.agents.order = 'random'

heli.params.add('strategy', 'Optimal Strategy', 'check', dflt=True)
heli.param('num_agent', 100)
heli.params['num_agent'].type = 'hidden'
heli.param('stopafter', 500)
heli.cumAvg = 0

#===============
# BEHAVIOR
#===============

#Set up boxes. Index is the box number, value is the number inside.
@heli.hook
def modelPreStep(model):
	model.boxes = [a.id for a in model.agents['agent']]
	shuffle(model.boxes)
	model.escaped = True

@heli.hook
def agentStep(agent, model, stage):
	agent.checked = []

	#Choose the box with your own number, then choose the box with the number
	#you find inside, and so on until you find your own number or run out.
	if model.param('strategy'):
		agent.checked.append(model.boxes[agent.id-1])
		while agent.id not in agent.checked and len(agent.checked) < 50:
			agent.checked.append(model.boxes[agent.checked[-1]-1])

	#Choose randomly for 50 boxes
	else:
		while agent.id not in agent.checked and len(agent.checked) < 50:
			box = randint(0, len(model.boxes)-1)
			while box in agent.checked: box = randint(0, len(model.boxes)-1)
			agent.checked.append(model.boxes[box])

	if agent.id not in agent.checked:
		model.escaped = False
		model.cutStep() #Go ahead and skip everyone else if anyone fails

@heli.hook
def modelPostStep(model):
	model.cumAvg = mean(model.data['escaped']+[model.escaped])

#===============
# DATA AND VISUALIZATION
#===============

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)
viz.dim = (950, 400)

heli.data.addReporter('escaped', heli.data.modelReporter('escaped'))
heli.data.addReporter('cumAvg', heli.data.modelReporter('cumAvg'))

caplot = viz.addPlot('cumAvg', 'Cumulative Average')
caplot.addSeries('cumAvg', 'Cumulative Average', '#C00')

#===============
# LAUNCH THE GUI
#===============

heli.launchCpanel()