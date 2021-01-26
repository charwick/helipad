# A model of the long-run cyclical dynamics of urbanization and human capital.

from collections import namedtuple
import pandas, random as rand2

from helipad import Helipad
from math import sqrt, log
from numpy import *
heli = Helipad()

#================
# CONFIGURATION
#================

heli.addBreed('urban', '#CC0000')
heli.addBreed('rural', '#00CC00')
heli.addGood('consumption', '#000000')

heli.addParameter('city', 'City?', 'check', True, desc='Whether agents have the possibility of moving to the city')
heli.addParameter('breedThresh', 'Breeding Threshold (φ)', 'slider', dflt=20, opts={'low':5, 'high': 500, 'step': 5}, desc='Proportional to the minimum wealth necessary to breed')
heli.addParameter('movecost', 'Moving Cost (ω)', 'slider', dflt=15, opts={'low':0, 'high': 150, 'step': 1}, desc='Cost incurred by moving location')
heli.addParameter('deathrate', 'Death Rate (θ)', 'slider', dflt=0.05, opts={'low':0, 'high': 0.25, 'step': 0.01})
heli.addParameter('rent', 'Variable cost (ρ)', 'slider', dflt=.2, opts={'low':0.1, 'high': 1, 'step': 0.1}, desc='Per-period cost-of-living, proportional to human capital')
heli.addParameter('fixed', 'Fixed cost (χ)', 'slider', dflt=.2, opts={'low':0, 'high': 1, 'step': 0.1}, desc='Per-period cost-of-living')
heli.param('num_agent', 150)

heli.name = 'Cities'
heli.stages = 2
heli.order = 'linear'

class Land():
	def __init__(self, loc):
		self.loc = loc
		self.input = 0
		self.product = 0
	
	def produce(self):
		self.product = log(self.input)	# = ln∑P (eq. 2)
		self.input = 0 #Reset productivity at the end of each period
		return self.product

heli.land = {k: Land(k) for k in ['urban', 'rural']}
heli.params['num_agent'].type = 'hidden'

#================
# AGENT BEHAVIOR
#================

#This is here to make sure that the agents param gets reset at the beginning of each run
#Otherwise the parameter persists between runs
@heli.hook
def modelPreSetup(model):
	model.movers = {b:0 for b in heli.primitives['agent'].breeds}
	model.births = {b:0 for b in heli.primitives['agent'].breeds}
	for b in heli.primitives['agent'].breeds:
		setattr(model, 'moverate'+b, 0)
		setattr(model, 'birthrate'+b, 0)
	
	#Mark the different phases of the Malthusian model
	model.clearEvents()
	if not model.param('city'):
		@heli.event
		def exp1(model):	return sum(diff(model.data.getLast('ruralPop', 20))) > 3
		@heli.event
		def taper2(model):	return model.events['exp1'].triggered and sum(diff(model.data.getLast('ruralPop', 20))) < -1
		@heli.event
		def cull3(model):	return model.events['taper2'].triggered and sum(diff(model.data.getLast('ruralH-25-pctile', 20))) > 2
		@heli.event
		def stab4(model):	return model.events['cull3'].triggered and sum(diff(model.data.getLast('ruralPop', 400))) > 0

# from helipad.utility import CobbDouglas
@heli.hook
def agentInit(agent, model):
	# agent.utility = CobbDouglas({'consumption': 0.5}) #Single good
	agent.H = 1 #Human capital
	agent.prod = {'urban': 0, 'rural': 0}
	agent.wealth = 0
	agent.lastWage = 0

#Distribute product in proportion to input
#modelStep executes each stage **before** any agent step functions
@heli.hook
def modelStep(model, stage):
	if stage==2:
		for l in model.land.values():
			inp = l.input								# = ∑P
			Y = l.produce()								# = ln∑P (eq. 2)
			for a in model.agent(l.loc):
				a.lastWage = a.prod[a.breed]/inp * Y	# = P/∑P * Y (eq. 3)
				a.wealth += a.lastWage

@heli.hook
def agentStep(agent, model, stage):
	if stage==1:
		upop = model.data.getLast('urbanPop')
		#Account for the effect of you moving on the mean, otherwise you get divide by zero for the first mover.
		agent.prod = {
			'rural': agent.H * sqrt(150),
			'urban': agent.H * sqrt(
				# (model.data.getLast('hsum')+agent.H)/sqrt(model.data.getLast('urbanPop')+1) if agent.breed=='rural'
				# else (model.data.getLast('hsum'))/sqrt(model.data.getLast('urbanPop'))
				model.data.getLast('urbanH')*log(model.data.getLast('hsum')) if agent.breed =='urban'
				else (model.data.getLast('urbanH')**(upop/(upop+1)) * agent.H**(1/(upop+1))) * log(model.data.getLast('hsum')+agent.H)
			)
		}	#(Eq. 1')
		
		if model.param('city'):
			otherloc = 'urban' if agent.breed == 'rural' else 'rural'
			oprod = exp(model.land[otherloc].product)+agent.prod[otherloc]
			otherwage = log(oprod)*agent.prod[otherloc]/oprod		
		
			#Decide whether or not to move
			mvc = model.param('movecost')
			if otherwage > agent.lastWage*1.25 and agent.wealth > mvc: #and model.t > 10000:
			# if agent.prod[otherloc]-mvc > agent.prod[agent.breed] and agent.wealth > mvc: #and model.t > 10000:
				# print('T=',model.t,', HC',agent.H,':',agent.breed,'wage=',agent.lastWage,',',otherloc,'wage=',otherwage)
				agent.wealth -= mvc
				model.movers[agent.breed] += 1
				agent.breed = otherloc

		model.land[agent.breed].input += agent.prod[agent.breed] #Work
		
		#Reproduce
		rand = random.randint(0,10000)/100 #uniform btw 0 & 100
		randn= random.normal(1, 0.2)
		if rand < model.param('deathrate'): agent.die()
		elif agent.wealth > model.param('breedThresh') * (randn if agent.breed=='rural' else agent.H/4):
			child = agent.reproduce(
				inherit=['H', ('wealth', lambda w: w[0]/2)],
				mutate={'H': (0.5, 'log')}
			)
			agent.wealth -= agent.wealth/2 + 1 #-= breedThresh #Fixed cost
			model.births[agent.breed] += 1
	
	#Get paid in modelStep, then pay rent
	elif stage==2:
		agent.wealth -= model.param('rent')/100 * agent.H + model.param('fixed')/100
		# agent.utils = agent.utility.calculate({'consumption': agent.wealth})
		if agent.wealth <= 0: agent.die()
		return

#Organize some data and pause if all agents are dead
@heli.hook
def modelPostStep(model):
	if len(model.agents['agent']) == 0: model.stop()
	else:
		for b in model.primitives['agent'].breeds:
			pop = len(model.agent(b))
			if pop > 0:
				setattr(model,'moverate'+b, model.movers[b]/pop)
				setattr(model,'birthrate'+b, model.births[b]/pop)
				model.movers[b] = 0
				model.births[b] = 0

@heli.hook
def decideBreed(id, choices, model):
	return 'rural';

#================
# REPORTERS AND PLOTS
#================

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)

def urbanPop(model): return len(model.agent('urban'))
def ruralPop(model): return len(model.agent('rural'))

# returns ln(∑H²) for urban population
@heli.reporter
def hsum(model):
	upop = model.agent('urban')
	return sum([a.H for a in model.agent('urban')]) if len(upop) > 0 else 1

def perCapGdp(model, loc):
	def tmp(model):
		pop = globals()[loc+'Pop'](model)
		if pop==0: return 0
		else: return model.land[loc].product/pop
	return tmp

viz.addPlot('pop', 'Population', 1, logscale=True)
viz.addPlot('hcap', 'Human Capital', 2, logscale=True)
viz.addPlot('wage', 'Wage', 3)
viz.addPlot('wealth', 'Wealth', 4, logscale=True)
viz.addPlot('rates', 'Rates', 5, logscale=True)
heli.data.addReporter('theta', lambda model: model.param('deathrate')/100)
viz.plots['rates'].addSeries('theta', 'Death Rate', '#CCCCCC')

for breed, d in heli.primitives['agent'].breeds.items():
	heli.data.addReporter(breed+'Pop', locals()[breed+'Pop'])
	heli.data.addReporter(breed+'H', heli.data.agentReporter('H', 'agent', breed=breed, stat='gmean', percentiles=[25,75]))
	heli.data.addReporter(breed+'Wage', perCapGdp(heli, breed))
	heli.data.addReporter(breed+'Wealth', heli.data.agentReporter('wealth', 'agent', breed=breed, stat='gmean'))
	heli.data.addReporter(breed+'moveRate', heli.data.modelReporter('moverate'+breed), smooth=0.98)
	heli.data.addReporter(breed+'birthrate', heli.data.modelReporter('birthrate'+breed), smooth=0.98)
	viz.plots['pop'].addSeries(breed+'Pop', breed.title()+' Population', d.color)
	viz.plots['hcap'].addSeries(breed+'H', breed.title()+' Human Capital', d.color)
	viz.plots['wage'].addSeries(breed+'Wage', breed.title()+' Wage', d.color)
	viz.plots['wealth'].addSeries(breed+'Wealth', breed.title()+' Wealth', d.color)
	viz.plots['rates'].addSeries(breed+'moveRate', breed.title()+' Move Rate', d.color2)
	viz.plots['rates'].addSeries(breed+'birthrate', breed.title()+' Birthrate', d.color)

heli.launchCpanel()

#Malthusian parameter sweep

# heli.param('csv', 'CSVs/malthusian')
# @heli.hook('modelPreSetup', prioritize=True)
# def turnOffCity(model): model.param('city', False)
# heli.param('stopafter', 15000)
# results = heli.paramSweep(['rent', 'fixed'])
# print([{e.name: e.triggered for e in run.events} for run in results])