# A group-selection model of the evolution of cooperation with deme extinction
# Loosely based on chapter 7.1 of Bowles and Gintis, "A Cooperative Species"

#===============
# SETUP
#===============

from helipad import Helipad, MultiLevel, Agent
from random import choice
import numpy.random as nprand
from math import exp, sqrt

heli = Helipad()
heli.name = 'Deme Selection'
heli.order = ['linear', 'linear', 'match']
heli.stages = 3 #Stage 1 for intra-demic competition, stage 2 for reproduction, stage 3 for war

heli.addPrimitive('deme', MultiLevel, dflt=20, priority=1)
heli.removePrimitive('agent')
heli.addParameter('b', 'Benefit conferred', 'slider', dflt=6, opts={'low': 0, 'high': 10, 'step': 1})
heli.addParameter('c', 'Cost incurred', 'slider', dflt=2, opts={'low': 0, 'high': 10, 'step': 1})
heli.addParameter('k', 'Likelihood of war', 'slider', dflt=0.25, opts={'low': 0, 'high': 1, 'step': 0.01})

#===============
# BEHAVIOR
#===============

def strength(self):
	return sum([a.stocks['payoff'] for a in self.agents['agent']])
MultiLevel.strength = property(strength)

def migrate(self, deme):
	self.model.agents['agent'].remove(self)
	self.model = deme
	deme.agents['agent'].append(self)
Agent.migrate = migrate	

def agentStep(agent, deme, stage):
	if agent.breed == 'altruist':
		beneficiary = choice(deme.agents['agent'])
		agent.stocks['payoff'] -= deme.model.param('c')
		beneficiary.stocks['payoff'] += deme.model.param('b')

#deme is the MultiLevel object, which inherits from both baseAgent and Helipad.
def demeInit(deme, model):
	deme.param('agents_agent', 20)
	deme.addBreed('altruist', '009900')
	deme.addBreed('selfish', '990000')
	deme.addGood('payoff', '000099', 1)
	deme.addHook('agentStep', agentStep)
heli.addHook('demeInit', demeInit)

#Odds of winning follow a sigmoid distribution in the difference in strength
def war(demes, primitive, model, stage):
	k = model.param('k')
	if not nprand.choice(2, 1, p=[1-k, k])[0]: return
	
	#Fight
	diff = (demes[0].strength - demes[1].strength)/10
	prob = 1/(1+exp(-diff))
	result = nprand.choice(2, 1, p=[prob, 1-prob])[0]
	
	#Colonize
	pop = len(demes[not result].agents['agent'])
	for a in demes[not result].agents['agent']: a.die()
	for i in range(pop):
		choice(demes[result].agents['agent']).reproduce().migrate(demes[not result])
heli.addHook('demeMatch', war)

def demeStep(deme, model, stage):
	if stage > 1: deme.dontStepAgents = True
	
	#Reproduce
	if stage==2:
		for a in deme.agents['agent']:
			for i in range(a.stocks['payoff']): a.reproduce()
			a.die()
heli.addHook('demeStep', demeStep)

#Normalize population at the beginning of stage 3
def modelStep(model, stage):
	if stage==3:
		for d in model.agents['deme']:
			targetDpop = 20
			while len(d.agents['agent']) > 20: choice(d.agents['agent']).die()
			while len(d.agents['agent']) < 20: choice(d.agents['agent']).reproduce()
heli.addHook('modelStep', modelStep)

#===============
# CONFIGURATION
#===============

def totalPop(model): return sum([len(d.agents['agent']) for d in model.agents['deme']])
def altruists(model): return sum([len(d.agent('altruist')) for d in model.agents['deme']])/totalPop(model)
def selfish(model): return sum([len(d.agent('selfish')) for d in model.agents['deme']])/totalPop(model)
def avgFitness(model): return sum([sum([a.stocks['payoff'] for a in d.agents['agent']]) for d in model.agents['deme']])/totalPop(model)
heli.data.addReporter('population', totalPop)
heli.data.addReporter('altruists', altruists)
heli.data.addReporter('selfish', selfish)
heli.data.addReporter('fitness', avgFitness)

heli.addPlot('pop', 'Population', selected=False)
heli.addPlot('pheno', 'Phenotypes', stack=True)
heli.addPlot('fitness', 'Fitness')
heli.addSeries('pop', 'population', 'Total population', '000000')
heli.addSeries('pheno', 'altruists', 'Altruists', '33CC33')
heli.addSeries('pheno', 'selfish', 'Selfish', 'BB2222')
heli.addSeries('fitness', 'fitness', 'Average Fitness', '000099')

#===============
# LAUNCH THE GUI
#===============

heli.launchGUI(headless=False)