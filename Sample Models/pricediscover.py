# A decentralized price discovery model with random matching

#===============
# SETUP
#===============

from model import Helipad
from utility import CobbDouglas
from math import sqrt, exp, floor
import random

heli = Helipad()
heli.order = 'random'

heli.addParameter('ratio', 'Log Endowment Ratio', 'slider', dflt=0, opts={'low': -3, 'high': 3, 'step': 0.5})

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0
	
	#Endowments
	agent.shmoo = random.randint(1,1000)
	agent.soma = random.randint(1,floor(exp(model.param('ratio'))*1000))
	
	#Utility
	coeff = random.randint(1,99)/100
	agent.utility = CobbDouglas(['shmoo', 'soma'])
heli.addHook('agentInit', agentInit)

def agentStep(agent, model, stage):
	if agent.lastPeriod == model.t: return #Already traded
	partner = random.choice(model.agents['agent']);
	while partner.lastPeriod == model.t: partner = random.choice(model.agents['agent']); #Don't trade with someone who's already traded
	
	myEndowU = agent.utility.calculate({'soma': agent.soma, 'shmoo': agent.shmoo})
	theirEndowU = partner.utility.calculate({'soma': partner.soma, 'shmoo': partner.shmoo})
	
	#Get the endpoints of the contract curve
	#Contract curve isn't linear unless the CD exponents are both 0.5. If not, *way* more complicated
	cc1Soma = myEndowU * ((agent.soma+partner.soma)/(agent.shmoo+partner.shmoo)) ** 0.5
	cc2Soma = agent.soma + partner.soma - theirEndowU  * ((agent.soma+partner.soma)/(agent.shmoo+partner.shmoo)) ** 0.5
	cc1Shmoo = ((agent.shmoo+partner.shmoo)/(agent.soma+partner.soma)) * cc1Soma
	cc2Shmoo = ((agent.shmoo+partner.shmoo)/(agent.soma+partner.soma)) * cc2Soma
		
	#Calculate demand – split the difference on the contract curve
	somaDemand = (cc1Soma+cc2Soma)/2 - agent.soma
	shmooDemand = (cc1Shmoo+cc2Shmoo)/2 - agent.shmoo
	
	#Do the trades
	if abs(somaDemand) > 0.1 and abs(shmooDemand) > 0.1:
		agent.soma += somaDemand
		partner.soma -= somaDemand
		agent.shmoo += shmooDemand
		partner.shmoo -= shmooDemand
		
		agent.lastPrice = -somaDemand/shmooDemand
		partner.lastPrice = -somaDemand/shmooDemand
	else:
		agent.lastPrice = None
		partner.lastPrice = None
			
	#Record data and don't trade again this period
	agent.lastPeriod = model.t
	partner.lastPeriod = model.t
	agent.utils = agent.utility.consume({'soma': agent.soma, 'shmoo': agent.shmoo})
	partner.utils = partner.utility.consume({'soma': partner.soma, 'shmoo': partner.shmoo})
	
	agent.somaTrade = abs(somaDemand)
	agent.shmooTrade = abs(shmooDemand)
	partner.somaTrade = 0 #Don't double count
	partner.shmooTrade = 0
	
heli.addHook('agentStep', agentStep)

#Stop the model when we're basically equilibrated
def modelStep(model, stage):
	if model.t > 1 and model.data.getLast('shmooTrade') < 0.5 and model.data.getLast('somaTrade') < 0.5:
		model.gui.terminate()
heli.addHook('modelStep', modelStep)

#===============
# CONFIGURATION
#===============

heli.data.addReporter('price', heli.data.agentReporter('lastPrice', 'agent', stat='gmean', percentiles=[0,100]))
heli.addSeries('prices', 'price', 'Soma/Shmoo Price', '119900')
heli.data.addReporter('somaTrade', heli.data.agentReporter('somaTrade', 'agent'))
heli.data.addReporter('shmooTrade', heli.data.agentReporter('shmooTrade', 'agent'))
heli.addSeries('demand', 'shmooTrade', 'Shmoo Trade', '990000')
heli.addSeries('demand', 'somaTrade', 'Soma Trade', '000099')

heli.defaultPlots = ['prices', 'demand', 'utility']

heli.launchGUI()