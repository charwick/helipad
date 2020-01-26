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

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0
	
	#Endowment
	agent.shmoo = random.randint(0,100)
	agent.soma = random.randint(0,100)
	
	#Utility
	coeff = random.randint(1,99)/100
	agent.utility = CobbDouglas(['shmoo', 'soma'], {'shmoo': coeff, 'soma': 1-coeff})
heli.addHook('agentInit', agentInit)

def agentStep(agent, model, stage):
	if agent.lastPeriod == model.t: return #Already traded
	partner = random.choice(model.agents);
	while partner.lastPeriod == model.t: partner = random.choice(model.agents); #Don't trade with someone who's already traded
	
	# Trade here
	q = {'soma': self.soma, 'shmoo': self.shmoo}
	curutil = agent.utility.calculate(q)
	mus = agent.utility.mu(q)
	
	partner.lastPeriod = model.t
	agent.lastPeriod = model.t
heli.addHook('agentStep', agentStep)

#===============
# CONFIGURATION
#===============

#series

heli.launchGUI()
