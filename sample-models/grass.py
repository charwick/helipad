# A sample spatial model with agents eating grass off patches.

#===============
# SETUP
#===============

from random import choice, randint
from numpy import mean
from helipad import Helipad

heli = Helipad()
heli.name = 'Grass Eating'
heli.agents.order = 'random'
heli.stages = 5

heli.params.add('energy', 'Energy from grass', 'slider', dflt=2, opts={'low': 2, 'high': 10, 'step': 1})
heli.params.add('smart', 'Smart consumption', 'check', dflt=True, desc='Move to the neighboring patch with the most grass, rather than randomly')
heli.params.add('e2reproduce', 'Energy to reproduce', 'slider', dflt=25, opts={'low': 0, 'high': 100, 'step': 5})
heli.params.add('maleportion', 'Male portion reproduction', 'slider', dflt=40, opts={'low': 0, 'high': 100, 'step': 5})
heli.params.add('maxLife', 'Max Lifespan', 'slider', dflt=200, opts={'low': 100, 'high': 1000, 'step': 10})
heli.params.add('grassrate', 'Grass Rate', 'slider', dflt=10, opts={'low': 1, 'high': 100, 'step': 1})

heli.params['num_agent'].opts = {'low': 1, 'high': 200, 'step': 1}
heli.param('num_agent', 200)

heli.agents.addBreed('male', 'blue')
heli.agents.addBreed('female', 'pink')
heli.goods.add('energy', 'red', 5)

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
			maxenergy = max(n.stocks['energy'] for n in agent.patch.neighbors)
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
def nofemales(model): return len(model.agents['agent']['female']) <= 1
heli.param('stopafter', 'nofemales')
heli.param('refresh', 1)

#===============
# DATA AND VISUALIZATION
#===============

heli.data.addReporter('grass', heli.data.agentReporter('stocks', 'patch', good='energy', stat='sum'))
heli.data.addReporter('age', heli.data.agentReporter('age', 'agent'))
heli.data.addReporter('num_agent', lambda model: len(model.agents['agent']))
heli.data.addReporter('sexratio', lambda model: len(model.agents['agent']['male'])/len(model.agents['agent']['female']))
heli.data.addReporter('expectancy', lambda model: mean(model.deathAge))
heli.data.addReporter('agentenergy', heli.data.agentReporter('stocks', 'agent', good='energy', percentiles=[0,100]))

mapPlot = heli.spatial(dim=16, corners=True)
mapPlot.scatter = ['age', 'good:energy']
mapPlot.config({
	'patchProperty': 'good:energy',
	'patchColormap': 'Greens',
	'agentSize': 'good:energy'
})

# # Only forward 0.368
# import geopandas,os
# __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
# gdf = geopandas.read_file(os.path.join(__location__, 'NC_Counties.geojson'))
# for i,county in gdf.iterrows():
#     heli.patches.add(county['geometry'], county['CO_NAME'])

pop = heli.visual.addPlot('pop', 'Population', 'timeseries', logscale=True, selected=False)
sexratio = heli.visual.addPlot('sexratio', 'Sex Ratio', 'timeseries', logscale=True, selected=False)
age = heli.visual.addPlot('age', 'Age', 'timeseries', selected=False)
energy = heli.visual.addPlot('energy', 'Energy', 'timeseries', selected=False)

pop.addSeries('num_agent', 'Population', 'black')
pop.addSeries('grass', 'Grass', 'green')
sexratio.addSeries('sexratio', 'M/F Sex Ratio', 'brown')
age.addSeries('age', 'Average Age', 'blue')
pop.addSeries('expectancy', 'Life Expectancy', 'black')
energy.addSeries('agentenergy', 'Energy', 'green')

@heli.hook
def agentClick(agent, plot, t):
	print([f'Agent {a.id} at ({a.x}, {a.y})' for a in agent if a is not None])

@heli.hook
def patchClick(patch, plot, t):
	print(patch)

#===============
# LAUNCH THE GUI
#===============

heli.launchCpanel()