# A decentralized price discovery model with random matching

#===============
# SETUP
#===============

from collections import namedtuple
import pandas, sys, random

from model import Helipad
from math import sqrt
heli = Helipad()

heli.order = 'random'

#===============
# BEHAVIOR
#===============

def agentInit(agent, model):
	agent.lastPeriod = 0
	agent.shmoo = random.randint(0,100)
heli.addHook('agentInit', agentInit)

def agentStep(agent, model, stage):
	if agent.lastPeriod == model.t: return #Already traded
	partner = random.choice(model.agents);
	while partner.lastPeriod == model.t: partner = random.choice(model.agents); #Don't trade with someone who's already traded
	
	# Trade here
	
	
	partner.lastPeriod = model.t
	agent.lastPeriod = model.t
	
heli.addHook('agentStep', agentStep)

heli.launchGUI()
