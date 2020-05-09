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

heli.addParameter('ratio', 'Log Endowment Ratio', 'slider', dflt=0, opts={'low': -3, 'high': 3, 'step': 0.5})
heli.addGood('shmoo','11CC00', lambda breed: random.randint(1,1000))
heli.addGood('soma', 'CC0000', lambda breed: random.randint(1,floor(exp(heli.param('ratio'))*1000)))

heli.params['agents_agent'].opts['step'] = 2 #Make sure we don't get stray agents

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0	
	agent.utility = CobbDouglas(['shmoo', 'soma'])
heli.addHook('agentInit', agentInit)

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
	agents[0].utils = agents[0].utility.consume({'soma': agents[0].stocks['soma'], 'shmoo': agents[0].stocks['shmoo']})
	agents[1].utils = agents[1].utility.consume({'soma': agents[1].stocks['soma'], 'shmoo': agents[1].stocks['shmoo']})
	
heli.addHook('match', match)

#Stop the model when we're basically equilibrated
def modelStep(model, stage):
	if model.t > 1 and model.data.getLast('demand-shmoo') < 20 and model.data.getLast('demand-soma') < 20:
		model.gui.terminate()
heli.addHook('modelStep', modelStep)

#===============
# CONFIGURATION
#===============

heli.data.addReporter('ssprice', heli.data.agentReporter('lastPrice', 'agent', stat='gmean', percentiles=[0,100]))
heli.addPlot('price', 'Price', logscale=True)
heli.addSeries('price', 'ssprice', 'Soma/Shmoo Price', '119900')

heli.defaultPlots = ['price', 'demand', 'utility']

heli.launchGUI()