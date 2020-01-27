# A decentralized price discovery model with random matching

#===============
# SETUP
#===============

from collections import namedtuple
import pandas, sys, random, agent
from utility import CobbDouglas

from model import Helipad
from math import sqrt
heli = Helipad()

heli.order = 'random'

#Set refresh rate to 1 since it goes quickly
def GUIPostInit(gui):
	gui.updateEvery = 1 #Not working…
heli.addHook('GUIPostInit', GUIPostInit)

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0
	
	#Endowment
	agent.shmoo = random.randint(1,100)
	agent.soma = random.randint(1,100)
	
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
	agent.soma += somaDemand
	partner.soma -= somaDemand
	agent.shmoo += shmooDemand
	partner.shmoo -= shmooDemand
			
	#Record utility and don't trade again this period
	partner.lastPeriod = model.t
	partner.utils = partner.utility.consume({'soma': partner.soma, 'shmoo': partner.shmoo})
	agent.lastPeriod = model.t
	agent.utils = agent.utility.consume({'soma': agent.soma, 'shmoo': agent.shmoo})
heli.addHook('agentStep', agentStep)

#===============
# CONFIGURATION
#===============

#series

heli.launchGUI()