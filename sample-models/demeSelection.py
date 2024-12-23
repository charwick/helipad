# A group-selection model of the evolution of cooperation with deme extinction
# Loosely based on chapter 7.1 of Bowles and Gintis, "A Cooperative Species"

#===============
# SETUP
#===============

from random import choice
from math import exp
import numpy.random as nprand
from helipad import Helipad, MultiLevel

def setup():
	heli = Helipad()
	heli.name = 'Deme Selection'
	heli.agents.order = ['linear', 'linear', 'match']
	heli.stages = 3 #Stage 1 for intra-demic competition, stage 2 for reproduction, stage 3 for war

	heli.agents.addPrimitive('deme', MultiLevel, dflt=20, priority=1)
	heli.agents.removePrimitive('agent')
	heli.params.add('b', 'Benefit conferred', 'slider', dflt=6, opts={'low': 0, 'high': 10, 'step': 1})
	heli.params.add('c', 'Cost incurred', 'slider', dflt=2, opts={'low': 0, 'high': 10, 'step': 1})
	heli.params.add('k', 'Likelihood of war', 'slider', dflt=0.25, opts={'low': 0, 'high': 1, 'step': 0.01})

#===============
# BEHAVIOR
#===============

	def strength(self):
		return sum(a.stocks['payoff'] for a in self.agents['agent'])
	MultiLevel.strength = property(strength)

	def agentStep(agent, deme, stage):
		if agent.breed == 'altruist':
			beneficiary = choice(deme.agents['agent'])
			agent.stocks['payoff'] -= deme.model.param('c')
			beneficiary.stocks['payoff'] += deme.model.param('b')

	#deme is the MultiLevel object, which inherits from both baseAgent and Helipad.
	@heli.hook
	def demeInit(deme, model):
		deme.param('num_agent', 20)
		deme.agents.addBreed('altruist', '#009900')
		deme.agents.addBreed('selfish', '#990000')
		deme.goods.add('payoff', '#000099', 1)
		deme.hooks.add('agentStep', agentStep)

	#Odds of winning follow a sigmoid distribution in the difference in strength
	@heli.hook('demeMatch')
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
			choice(demes[result].agents['agent']).reproduce().transfer(demes[not result])

	@heli.hook
	def demeStep(deme, model, stage):
		if stage > 1: deme.cutStep()

		#Reproduce
		if stage==2:
			for a in deme.agents['agent']:
				for i in range(a.stocks['payoff']): a.reproduce()
				a.die()

	#Normalize population at the beginning of stage 3
	@heli.hook
	def modelStep(model, stage):
		if stage==3:
			targetDpop = 20
			for d in model.agents['deme']:
				while len(d.agents['agent']) > targetDpop: choice(d.agents['agent']).die()
				while len(d.agents['agent']) < targetDpop: choice(d.agents['agent']).reproduce()

#===============
# DATA & VISUALIZATION
#===============

	from helipad.visualize import TimeSeries
	viz = heli.useVisual(TimeSeries)

	@heli.reporter
	def population(model): return sum(len(d.agents['agent']) for d in model.agents['deme'])
	@heli.reporter
	def altruists(model): return sum(len(d.agents['agent']['altruist']) for d in model.agents['deme'])/population(model)
	@heli.reporter
	def selfish(model): return sum(len(d.agents['agent']['selfish']) for d in model.agents['deme'])/population(model)
	@heli.reporter
	def fitness(model): return sum(sum(a.stocks['payoff'] for a in d.agents['agent']) for d in model.agents['deme'])/population(model)

	viz.addPlot('pop', 'Population', selected=False)
	viz.addPlot('pheno', 'Phenotypes', stack=True)
	viz.addPlot('fitness', 'Fitness')
	viz['pop'].addSeries('population', 'Total population', '#000000')
	viz['pheno'].addSeries('altruists', 'Altruists', '#33CC33')
	viz['pheno'].addSeries('selfish', 'Selfish', '#BB2222')
	viz['fitness'].addSeries('fitness', 'Average Fitness', '#000099')

	return heli

#===============
# LAUNCH THE GUI
#===============

if __name__ == '__main__':
	heli = setup()
	heli.launchCpanel()