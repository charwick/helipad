# For instructions on how to run, see http://cameronharwick.com/running-a-python-abm/

from collections import namedtuple
import pandas

from model import Helipad
from math import sqrt, log
from agent import * #Necessary for callback to figure out if is instance of hAgent
import random as rand2
heli = Helipad()

#================
# CONFIGURATION
#================

heli.addBreed('urban', 'CC0000')
heli.addBreed('rural', '00CC00')
heli.addGood('consumption', '000000')

#We don't need banks or stores
heli.params['banks'][1]['type'] = 'hidden'
heli.params['stores'][1]['type'] = 'hidden'
heli.params['agents'][1]['type'] = 'hidden'
heli.param('banks', 0)
heli.param('stores', 0)
heli.param('M0', False) #Indicates non-monetary economy
heli.addParameter('breedThresh', 'Breeding Threshold', 'slider', dflt=20, opts={'low':5, 'high': 500, 'step': 5}, desc='Proportional to the minimum wealth necessary to breed')
heli.addParameter('movecost', 'Moving Cost', 'slider', dflt=5, opts={'low':0, 'high': 150, 'step': 1}, desc='Cost incurred by moving location')
heli.addParameter('deathrate', 'Death Rate', 'slider', dflt=0.05, opts={'low':0, 'high': 0.25, 'step': 0.01})
heli.addParameter('rent', 'Rent', 'slider', dflt=.2, opts={'low':0, 'high': 1, 'step': 0.1}, desc='Per-period cost-of-living')
del heli.plots['inventory']

heli.stages = 2
heli.order = 'linear'

class Land():
	def __init__(self, model, loc):
		self.loc = loc
		self.input = 0
		self.model = model
		self.product = 0
	
	def produce(self):
		self.product = log(self.input)
		self.input = 0 #Reset productivity at the end of each period
		return self.product

heli.land = {k: Land(heli, k) for k in ['urban', 'rural']}

#================
# AGENT BEHAVIOR
#================

def modelPreSetup(model):
	model.movers = {b:0 for b in model.breeds}
	model.births = {b:0 for b in model.breeds}
	for b in model.breeds:
		setattr(model, 'moverate'+b, 0)
		setattr(model, 'birthrate'+b, 0)
heli.addHook('modelPreSetup', modelPreSetup)

from utility import CobbDouglas
def agentInit(agent, model):
	agent.utility = CobbDouglas(['consumption'], {'consumption': 0.5}) #Single good
	agent.H = 1 #Human capital
	agent.prod = {'urban': 0, 'rural': 0}
	agent.wealth = 0
	agent.children = 0
	agent.lastWage = 0
heli.addHook('agentInit', agentInit)

#Distribute product in proportion to input
def modelStep(model, stage):
	if stage==2:
		for l in model.land.values():
			inp = l.input
			product = l.produce()
			for a in model.agent(l.loc):
				a.lastWage = a.prod[a.breed]/inp * product	#Exp(product) undoes the ln(). See eq. 3
				a.wealth += a.lastWage
heli.addHook('modelStep', modelStep)

def modelPostStep(model):
	if len(model.agents) == 0: model.gui.pause()
	else:
		for b in model.breeds:
			pop = len(model.agent(b))
			if pop > 0:
				setattr(model,'moverate'+b, model.movers[b]/pop)
				setattr(model,'birthrate'+b, model.births[b]/pop)
				model.movers[b] = 0
				model.births[b] = 0
heli.addHook('modelPostStep', modelPostStep)

def agentStep(agent, model, stage):
	if stage==1:
		agent.prod = {
			'rural': agent.H * 150,	#sqrt(150)
			'urban': agent.H * (
				(model.data.getLast('hsum')+agent.H)/sqrt(model.data.getLast('urbanPop')+1) if agent.breed=='rural'
				else (model.data.getLast('hsum'))/sqrt(model.data.getLast('urbanPop'))
			)
		}
		otherloc = 'urban' if agent.breed == 'rural' else 'rural'
		
		#Decide whether or not to move
		mvc = model.param('movecost')
		if agent.prod[otherloc]-mvc > agent.prod[agent.breed] and agent.wealth > mvc: #and model.t > 10000:
			agent.wealth -= mvc
			model.movers[agent.breed] += 1
			agent.breed = otherloc

		model.land[agent.breed].input += agent.prod[agent.breed] #Work
		
		#Reproduce
		rand = random.randint(0,10000)/100 #uniform btw 0 & 100
		randn= random.normal(1, 0.2)
		if rand < model.param('deathrate'): agent.die()
		elif agent.wealth > model.param('breedThresh') * (randn if agent.breed=='rural' else agent.H/4):
			# print('randn was',randn,'Reproducing with wealth',agent.wealth)
			agent.reproduce({'H': (0.5, 'log')})
			agent.wealth -= agent.wealth/2 + 1 #-= breedThresh #Fixed cost
			model.births[agent.breed] += 1
	
	#Get paid
	elif stage==2:
		agent.wealth -= model.param('rent')/100 * agent.H
		# agent.utils = agent.utility.calculate({'consumption': n})
		if agent.wealth <= 0: agent.die()
		return
	
heli.addHook('agentStep', agentStep)

def agentReproduce(agent, child, model):
	agent.children += 1
	child.children = 0
	child.wealth = agent.wealth/2
heli.addHook('agentReproduce', agentReproduce)

#This is here to make sure that the agents param gets reset at the beginning of each run
#Otherwise the parameter persists between runs
def modelPreSetup(model):
	model.param('agents', 150)
heli.addHook('modelPreSetup', modelPreSetup)

def decideBreed(id, model):
	return 'rural';
heli.addHook('decideBreed', decideBreed)

#================
# REPORTERS AND PLOTS
#================

def urbanPop(model):
	u=0
	for a in model.agents:
		if a.breed == 'urban':
			u += 1
	return u
	
def ruralPop(model):
	return model.param('agents') - urbanPop(model)

# returns ln(∑H²)
def HSum(model):
	upop = model.agent('urban')
	if len(upop) > 0:
		h=0
		for a in model.agent('urban'): h += a.H
		return h
	else: return 1

def perCapGdp(model, loc):
	def tmp(model):
		pop = globals()[loc+'Pop'](model)
		if pop==0: return 0
		else: return model.land[loc].product/pop
	return tmp


heli.addPlot('pop', 'Population', 1, logscale=True)
heli.addPlot('hcap', 'Human Capital', 2, logscale=True)
heli.addPlot('wage', 'Wage', 3)
heli.addPlot('wealth', 'Wealth', 4, logscale=True)
heli.addPlot('rates', 'Rates', 5, logscale=True)
heli.defaultPlots.extend(['pop', 'hcap', 'wage', 'wealth', 'rates'])
heli.data.addReporter('hsum', HSum)
heli.data.addReporter('theta', lambda model: model.param('deathrate')/100)
heli.addSeries('rates', 'theta', 'Death Rate', 'CCCCCC')

for breed, d in heli.breeds.items():
	heli.data.addReporter(breed+'Pop', locals()[breed+'Pop'])
	heli.data.addReporter(breed+'H', heli.data.agentReporter('H', breed, 'gmean', percentiles=[25,75]))
	heli.data.addReporter(breed+'Wage', perCapGdp(heli, breed))
	heli.data.addReporter(breed+'Wealth', heli.data.agentReporter('wealth', breed, 'gmean'))
	heli.data.addReporter(breed+'moveRate', heli.data.modelReporter('moverate'+breed), smooth=0.98)
	heli.data.addReporter(breed+'birthrate', heli.data.modelReporter('birthrate'+breed), smooth=0.98)
	heli.addSeries('pop', breed+'Pop', breed.title()+' Population', d.color)
	heli.addSeries('hcap', breed+'H', breed.title()+' Human Capital', d.color)
	heli.addSeries('wage', breed+'Wage', breed.title()+' Wage', d.color)
	heli.addSeries('wealth', breed+'Wealth', breed.title()+' Wealth', d.color)
	heli.addSeries('rates', breed+'moveRate', breed.title()+' Move Rate', d.color2)
	heli.addSeries('rates', breed+'birthrate', breed.title()+' Birthrate', d.color)

heli.launchGUI()