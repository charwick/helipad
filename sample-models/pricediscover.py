# A decentralized price discovery model with random matching

#===============
# SETUP
#===============

from helipad import Helipad
from helipad.utility import CobbDouglas
from math import sqrt, exp, floor
import random

heli = Helipad()
heli.order = 'random'

heli.addParameter('ratio', 'Log Endowment Ratio', 'slider', dflt=0, opts={'low': -3, 'high': 3, 'step': 0.5})
heli.addGood('shmoo','11CC00', lambda breed: random.randint(1,1000))
heli.addGood('soma', 'CC0000', lambda breed: random.randint(1,floor(exp(heli.param('ratio'))*1000)))

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0	
	agent.utility = CobbDouglas(['shmoo', 'soma'])
heli.addHook('agentInit', agentInit)

def agentStep(agent, model, stage):
	if agent.lastPeriod == model.t: return #Already traded
	partner = random.choice(model.agents['agent']);
	while partner.lastPeriod == model.t: partner = random.choice(model.agents['agent']) #Don't trade with someone who's already traded
	
	myEndowU = agent.utility.calculate({'soma': agent.goods['soma'], 'shmoo': agent.goods['shmoo']})
	theirEndowU = partner.utility.calculate({'soma': partner.goods['soma'], 'shmoo': partner.goods['shmoo']})
	
	#Get the endpoints of the contract curve
	#Contract curve isn't linear unless the CD exponents are both 0.5. If not, *way* more complicated
	cc1Soma = myEndowU * ((agent.goods['soma']+partner.goods['soma'])/(agent.goods['shmoo']+partner.goods['shmoo'])) ** 0.5
	cc2Soma = agent.goods['soma'] + partner.goods['soma'] - theirEndowU  * ((agent.goods['soma']+partner.goods['soma'])/(agent.goods['shmoo']+partner.goods['shmoo'])) ** 0.5
	cc1Shmoo = ((agent.goods['shmoo']+partner.goods['shmoo'])/(agent.goods['soma']+partner.goods['soma'])) * cc1Soma
	cc2Shmoo = ((agent.goods['shmoo']+partner.goods['shmoo'])/(agent.goods['soma']+partner.goods['soma'])) * cc2Soma
		
	#Calculate demand: choose a random point on the contract curve
	r = random.random()
	somaDemand = r*cc1Soma + (1-r)*cc2Soma - agent.goods['soma']
	shmooDemand = r*cc1Shmoo + (1-r)*cc2Shmoo - agent.goods['shmoo']
	
	#Do the trades
	if abs(somaDemand) > 0.1 and abs(shmooDemand) > 0.1:
		agent.trade(partner, 'soma', -somaDemand, 'shmoo', shmooDemand)
		agent.lastPrice = -somaDemand/shmooDemand
		partner.lastPrice = -somaDemand/shmooDemand
	else:
		agent.lastPrice = None
		partner.lastPrice = None
			
	#Record data and don't trade again this period
	agent.lastPeriod = model.t
	partner.lastPeriod = model.t
	agent.utils = agent.utility.consume({'soma': agent.goods['soma'], 'shmoo': agent.goods['shmoo']})
	partner.utils = partner.utility.consume({'soma': partner.goods['soma'], 'shmoo': partner.goods['shmoo']})
	
heli.addHook('agentStep', agentStep)

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