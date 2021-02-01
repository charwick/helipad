# A decentralized price discovery model with random matching

#===============
# SETUP
#===============

from helipad import Helipad
from helipad.utility import CobbDouglas
from math import sqrt, exp, floor
import random

heli = Helipad()
heli.name = 'Price Discover'
heli.order = 'match'

heli.addParameter('ratio', 'Log Endowment Ratio', 'slider', dflt=0, opts={'low': -3, 'high': 3, 'step': 0.5}, runtime=False)
heli.params['num_agent'].opts['step'] = 2 #Make sure we don't get stray agents

heli.addGood('shmoo','#11CC00', (1, 1000))
heli.addGood('soma', '#CC0000', lambda breed: (1, floor(exp(heli.param('ratio'))*1000)))

#===============
# BEHAVIOR
#===============

@heli.hook
def agentInit(agent, model):
	agent.utility = CobbDouglas(['shmoo', 'soma'])

@heli.hook
def match(agents, primitive, model, stage):
	myEndowU = agents[0].utility.calculate(agents[0].stocks)
	theirEndowU = agents[1].utility.calculate(agents[1].stocks)
	
	#Get the endpoints of the contract curve
	#Contract curve isn't linear unless the CD exponents are both 0.5. If not, *way* more complicated
	cc1Soma = myEndowU * (sum([a.stocks['soma'] for a in agents])/sum([a.stocks['shmoo'] for a in agents])) ** 0.5
	cc2Soma = sum([a.stocks['soma'] for a in agents]) - theirEndowU  * (sum([a.stocks['soma'] for a in agents])/sum([a.stocks['shmoo'] for a in agents])) ** 0.5
	cc1Shmoo = sum([a.stocks['shmoo'] for a in agents])/sum([a.stocks['soma'] for a in agents]) * cc1Soma
	cc2Shmoo = sum([a.stocks['shmoo'] for a in agents])/sum([a.stocks['soma'] for a in agents]) * cc2Soma
		
	#Calculate demand: choose a random point on the contract curve
	r = random.random()
	somaDemand = r*cc1Soma + (1-r)*cc2Soma - agents[0].stocks['soma']
	shmooDemand = r*cc1Shmoo + (1-r)*cc2Shmoo - agents[0].stocks['shmoo']
	
	#Do the trades
	if abs(somaDemand) > 0.1 and abs(shmooDemand) > 0.1:
		agents[0].trade(agents[1], 'soma', -somaDemand, 'shmoo', shmooDemand)
		agents[0].lastPrice = -somaDemand/shmooDemand
		agents[1].lastPrice = -somaDemand/shmooDemand
	else:
		agents[0].lastPrice = None
		agents[1].lastPrice = None
			
	#Record data
	agents[0].utils = agents[0].utility.calculate(agents[0].stocks)
	agents[1].utils = agents[1].utility.calculate(agents[1].stocks)

#Stop the model when we're basically equilibrated
@heli.event
def stopCondition(model):
	return model.t > 1 and model.data.getLast('demand-shmoo') < 20 and model.data.getLast('demand-soma') < 20
heli.param('stopafter', 'stopCondition')

#===============
# DATA AND VISUALIZATION
#===============

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)

heli.data.addReporter('ssprice', heli.data.agentReporter('lastPrice', 'agent', stat='gmean', percentiles=[0,100]))
pricePlot = viz.addPlot('price', 'Price', logscale=True, selected=True)
pricePlot.addSeries('ssprice', 'Soma/Shmoo Price', '#119900')

for p in ['demand', 'utility']: viz.plots[p].active(True)
heli.param('refresh', 1)

heli.launchCpanel()