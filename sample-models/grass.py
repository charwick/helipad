# A sample spatial model with agents eating grass off patches.
# No visualization as of yet

#===============
# SETUP
#===============

from helipad import Helipad

heli = Helipad()
heli.name = 'Grass Eating'
heli.order = 'random'
heli.stages = 5

heli.addParameter('energy', 'Energy from grass', 'slider', dflt=2, opts={'low': 2, 'high': 10, 'step': 1})
heli.addParameter('smart', 'Smart consumption', 'check', dflt=True)
heli.addParameter('e2reproduce', 'Energy to reproduce', 'slider', dflt=25, opts={'low': 0, 'high': 100, 'step': 5})
heli.addParameter('maleportion', 'Male portion reproduction', 'slider', dflt=40, opts={'low': 0, 'high': 100, 'step': 5})
heli.addParameter('maxLife', 'Max Lifespan', 'slider', dflt=200, opts={'low': 100, 'high': 1000, 'step': 10})
heli.addParameter('grassrate', 'Grass Rate', 'slider', dflt=10, opts={'low': 1, 'high': 100, 'step': 1})

heli.params['num_agent'].opts = {'low': 1, 'high': 200, 'step': 1}
heli.param('num_agent', 200)

heli.addBreed('male', 'blue')
heli.addBreed('female', 'pink')
heli.addGood('energy', 'red', 5)

from random import choice, randint
from numpy import mean

#===============
# BEHAVIOR
#===============

#Dividing it into stages like this (like in the NetLogo version) appears to make it more viable,
#perhaps because it encourages bunching onto the same fecund patch, with more opportunities for
#reproduction, whereas if they do it all at once, they avoid each other too much

@heli.hook
def agentStep(agent, model, stage):
	
	#Look for the neighboring patch with the most grass and move to it, if smart
	if stage==1:
		if model.param('smart'):
			maxenergy = max([n.stocks['energy'] for n in agent.patch.neighbors])
			prospects = [n for n in agent.patch.neighbors if n.stocks['energy'] == maxenergy]
		else: prospects = agent.patch.neighbors
		agent.orientTo(choice(prospects))
		agent.forward()
		agent.stocks['energy'] -= 1
	
	#Eat grass
	elif stage==2:
		if agent.patch.stocks['energy'] > 0:
			agent.patch.stocks['energy'] -= 1
			agent.stocks['energy'] += model.param('energy')
	
	#Reproduce
	elif stage==3:
		if agent.breed == 'male':
			e = model.param('e2reproduce')
			p = model.param('maleportion')
			me, fe = e*p/100, e*(100-p)/100
			if agent.stocks['energy'] > me:
				prospects = [f for f in agent.patch.agentsOn if f.breed=='female' and f.stocks['energy']>fe]
				if len(prospects):
					mate = choice(prospects)
					agent.stocks['energy'] -= me
					mate.stocks['energy'] -= fe
					child = mate.reproduce(inherit=[('breed', 'rand')], partners=[agent])
					child.stocks['energy'] = e
	
	#Die
	elif stage==4:
		if agent.stocks['energy'] <= 0 or agent.age > model.param('maxLife'):
			agent.die()
			model.deathAge.append(agent.age)
			if len(model.deathAge) > 100: model.deathAge.pop(0)

@heli.hook
def patchStep(patch, model, stage):
	#Regrow grass
	if stage==5 and patch.stocks['energy'] < 5 and randint(1,100) <= model.param('grassrate'):
		patch.stocks['energy'] += 1

@heli.hook
def modelPostSetup(model):
	model.deathAge = []

#Stop the model when we have no more females left to reproduce
@heli.event
def nofemales(model): return len(model.agent('female')) <= 1
heli.param('stopafter', 'nofemales')
heli.param('refresh', 1)

#===============
# DATA AND VISUALIZATION
#===============

# from helipad.visualize import TimeSeries
# viz = heli.useVisual(TimeSeries)

# viz.addPlot('pop', 'Population', logscale=True)
# viz.addPlot('sexratio', 'Sex Ratio', logscale=True)
# viz.addPlot('age', 'Age')
# viz.addPlot('energy', 'Energy')
heli.data.addReporter('grass', heli.data.agentReporter('stocks', 'patch', good='energy', stat='sum'))
heli.data.addReporter('age', heli.data.agentReporter('age', 'agent'))
heli.data.addReporter('num_agent', lambda model: len(model.agents['agent']))
heli.data.addReporter('sexratio', lambda model: len(model.agent('male', 'agent'))/len(model.agent('female', 'agent')))
heli.data.addReporter('expectancy', lambda model: mean(model.deathAge))
heli.data.addReporter('agentenergy', heli.data.agentReporter('stocks', 'agent', good='energy', percentiles=[0,100]))
# viz.plots['pop'].addSeries('num_agent', 'Population', 'black')
# viz.plots['pop'].addSeries('grass', 'Grass', 'green')
# viz.plots['sexratio'].addSeries('sexratio', 'M/F Sex Ratio', 'brown')
# viz.plots['age'].addSeries('age', 'Average Age', 'blue')
# viz.plots['pop'].addSeries('expectancy', 'Life Expectancy', 'black')
# viz.plots['energy'].addSeries('agentenergy', 'Energy', 'green')

mapPlot = heli.spatial(x=16, diag=True)
mapPlot.config('patchProperty', 'good:energy')
mapPlot.config('patchColormap', 'Greens')
mapPlot.config('agentSize', 'good:energy')

@heli.hook
def spatialAgentClick(agent, plot, t):
	print([a.position for a in agent if a is not None])

@heli.hook
def spatialPatchClick(patch, plot, t):
	print('Patch at',patch.position)

#===============
# LAUNCH THE GUI
#===============

heli.launchCpanel()