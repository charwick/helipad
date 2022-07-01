# A model of the long-run cyclical dynamics of urbanization and human capital.

from math import sqrt, log, floor, exp
from helipad import Helipad
from numpy import *
heli = Helipad()

#================
# CONFIGURATION
#================

heli.addBreed('urban', '#CC0000')
heli.addBreed('rural', '#00CC00')

#Constrain the parameter space to values resulting in H* = 100
def constrain(model, var, val):
	if var=='city': model.params['rent'].disabled(val)
	elif model.param('city'):
		if var=='fixed':
			model.params['rent'].enable() #Tkinter won't let you update the value of a disabled widget...
			model.param('rent', .04+.037*val)
			model.params['rent'].disable()
		# if var=='rent':
		# 	model.params['fixed'].enable() #Tkinter won't let you update the value of a disabled widget...
		# 	model.param('fixed', 24.7777*val-.9284659)
		# 	model.params['fixed'].disable()

heli.params.add('city', 'City?', 'check', True, desc='Whether agents have the possibility of moving to the city', runtime=False, callback=constrain)
heli.params.add('lockH', 'Lock human capital', 'check', False, desc='Maintains the distribution of human capital when checked')
heli.params.add('breedThresh', 'Breeding Threshold (φ)', 'slider', dflt=20, opts={'low':5, 'high': 500, 'step': 5}, desc='Proportional to the minimum wealth necessary to breed')
heli.params.add('movecost', 'Moving Cost (ω)', 'slider', dflt=10, opts={'low':0, 'high': 150, 'step': 1}, desc='Cost incurred by moving location')
heli.params.add('deathrate', 'Death Rate (θ)', 'slider', dflt=0.005, opts={'low':0, 'high': 0.05, 'step': 0.001})
heli.params.add('rent', 'Variable cost (ρ)', 'slider', dflt=.04, opts={'low':0.01, 'high': 0.1, 'step': 0.01}, desc='Per-period cost-of-living, proportional to human capital', callback=constrain)
heli.params.add('fixed', 'Fixed cost (χ)', 'slider', dflt=.4, opts={'low':0, 'high': 1, 'step': 0.1}, desc='Per-period cost-of-living', callback=constrain)

heli.name = 'Cities'
heli.stages = 2
heli.order = 'linear'

popfactor = 10 #Multiplies the productivity and therefore the equilibrium population, without changing anything else
burnout = 2000 #The end period, once it's equilibrated, over which to average the values

class Land():
	def __init__(self, loc):
		self.loc = loc
		self.input = 0
		self.lastInput = 0
		self.product = 0
	
	def produce(self):
		self.product = popfactor*log(self.input) #if self.loc=='rural' else sqrt(self.input)	# = ln∑P (eq. 2)
		self.lastInput = self.input
		self.input = 0 #Reset productivity at the end of each period
		return self.product
	
	def pop(self, model): return len(model.agent(self.loc))
	
	#The add argument calculates the productivity as if the agent were already there, if he's not
	def agentProd(self, H, add=False):
		if self.loc=='rural': return sqrt(150) * H
		else:
			if add:
				return 1/sqrt(self.pop(heli)+1) * (heli.data.getLast('hsum')+H)
				# return (heli.data.getLast('urbanH')*p+H)/(p+1) * log(heli.data.getLast('hsum')+H) #wtf was I doing here?
			else: return 1/sqrt(self.pop(heli)) * heli.data.getLast('hsum')
			# else: return heli.data.getLast('urbanH')*log(heli.data.getLast('hsum'))
	
	def expWage(self, H):
		prod = self.agentProd(H, True)
		potentialprod = log(self.lastInput+prod) #if self.loc=='rural' else sqrt(self.lastInput+prod)
		return potentialprod *  prod/(self.lastInput+prod) #Your share of the product

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
	model.deaths = 0
	for b in heli.primitives['agent'].breeds:
		setattr(model, 'moverate'+b, 0)
		setattr(model, 'birthrate'+b, 0)
	model.deathrate = 0
	
	#Mark the different phases of the Malthusian model
	model.events.clear()
	if not model.param('city'):
		model.param('num_agent', 150)
		@heli.event
		def exp1(model):	return sum(diff(model.data.getLast('ruralPop', 20))) > 3
		@heli.event
		def stab2(model):	return model.events['exp1'].triggered and model.t > model.events['exp1'].triggered+1000 and sum(diff(model.data.getLast('ruralH', 3000))) < 0
		@heli.event
		def end3(model): return model.events['stab2'].triggered and model.t >= model.events['stab2'].triggered + burnout
	
	#Start with the equilibrium population
	else: model.param('num_agent', math.floor(2.55-1.69*model.param('fixed'))*popfactor)

@heli.hook
def agentInit(agent, model):
	agent.H = random.normal(100, 15) if model.param('city') else 10 #Human capital
	agent.prod = 0
	agent.wealth = model.param('breedThresh') + model.param('rent')*10
	agent.lastWage = 0
	agent.expwage = 0

#Distribute product in proportion to input
#modelStep executes each stage **before** any agent step functions
@heli.hook
def modelStep(model, stage):
	if stage==2:
		for l in model.land.values():
			inp = l.input								# = ∑P
			Y = l.produce()								# = ln∑P (eq. 2)
			for a in model.agent(l.loc):
				a.lastWage = a.prod/inp * Y	# = P/∑P * Y (eq. 3)
				a.wealth += a.lastWage

@heli.hook
def agentStep(agent, model, stage):
	if stage==1:
		if model.param('city'):
			otherloc = 'urban' if agent.breed == 'rural' else 'rural'
			agent.expwage = model.land[otherloc].expWage(agent.H)
		
			#Decide whether or not to move
			mvc = model.param('movecost')
			if agent.expwage > agent.lastWage*1.2 and agent.wealth > mvc and model.t > 2:
			# if agent.prod[otherloc]-mvc > agent.prod[agent.breed] and agent.wealth > mvc: #and model.t > 10000:
				# print('T=',model.t,', HC',agent.H,':',agent.breed,'wage=',agent.lastWage,',',otherloc,'wage=',otherwage)
				agent.wealth -= mvc
				model.movers[agent.breed] += 1
				agent.breed = otherloc
				
		agent.prod = model.land[agent.breed].agentProd(agent.H)
		model.land[agent.breed].input += agent.prod #Work
		
		#Reproduce
		randn = random.normal(1, 0.2)
		if random.random() < model.param('deathrate'): agent.die()
		elif agent.wealth > model.param('breedThresh') * (randn if agent.breed=='rural' else agent.H/4):
			child = agent.reproduce(
				inherit=['H', ('wealth', lambda w: w[0]/2)],
				mutate={'H': 14.25} if not model.param('lockH') else {} #See footnote 3 for derivation
			)
			agent.wealth -= agent.wealth/2 + 1 #-= breedThresh #Fixed cost
			model.births[agent.breed] += 1
			if child.H < 2: child.die()
	
	#Get paid in modelStep, then pay rent
	elif stage==2:
		agent.wealth -= model.param('rent') * agent.H + model.param('fixed')
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
		model.deathrate = model.deaths/len(model.agents['agent'])
		model.deaths = 0

@heli.hook
def decideBreed(id, choices, model):
	return 'rural';

@heli.hook
def agentDie(agent): heli.deaths += 1

#================
# REPORTERS AND PLOTS
#================

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)

# returns ln(∑H²)
@heli.reporter
def hsum(model, loc='urban'):
	upop = model.agent(loc)
	return sum([a.H for a in upop]) if len(upop) > 0 else 1

def perCapGdp(model, loc):
	def tmp(model):
		pop = model.land[loc].pop(model)
		if pop==0: return 0
		else: return model.land[loc].product/pop
	return tmp

viz.addPlot('pop', 'Population', 1, logscale=True)
viz.addPlot('hcap', 'Human Capital', 2)
viz.addPlot('wage', 'Wage', 3)
viz.addPlot('wealth', 'Wealth', 4)
viz.addPlot('rates', 'Rates', 5, logscale=True)
heli.data.addReporter('theta', heli.data.modelReporter('deathrate'), smooth=0.99)
viz.plots['rates'].addSeries('theta', 'Death Rate', '#CCCCCC')

for breed, d in heli.primitives['agent'].breeds.items():
	heli.data.addReporter(breed+'Pop', heli.land[breed].pop)
	heli.data.addReporter(breed+'H', heli.data.agentReporter('H', 'agent', breed=breed, percentiles=[25,75]))
	heli.data.addReporter(breed+'Wage', heli.data.agentReporter('lastWage', 'agent', breed=breed, percentiles=[25,75]))
	heli.data.addReporter(breed+'ExpWage', heli.data.agentReporter('expwage', 'agent', breed=breed, percentiles=[25,75]))
	heli.data.addReporter(breed+'Wealth', heli.data.agentReporter('wealth', 'agent', breed=breed, percentiles=[25,75]))
	heli.data.addReporter(breed+'moveRate', heli.data.modelReporter('moverate'+breed), smooth=0.99)
	heli.data.addReporter(breed+'birthrate', heli.data.modelReporter('birthrate'+breed), smooth=0.99)
	viz.plots['pop'].addSeries(breed+'Pop', breed.title()+' Population', d.color)
	viz.plots['hcap'].addSeries(breed+'H', breed.title()+' Human Capital', d.color)
	viz.plots['wage'].addSeries(breed+'Wage', breed.title()+' Wage', d.color)
	viz.plots['wage'].addSeries(breed+'ExpWage', breed.title()+' Expected Wage', d.color2, visible=False)
	viz.plots['wealth'].addSeries(breed+'Wealth', breed.title()+' Wealth', d.color)
	viz.plots['rates'].addSeries(breed+'moveRate', breed.title()+' Moveaway Rate', d.color2)
	viz.plots['rates'].addSeries(breed+'birthrate', breed.title()+' Birthrate', d.color)

heli.launchCpanel()

#================
# PARAM SWEEP & ANALYSIS
#================

# for p in viz.plots.values(): p.active(False) #Disable plots so Helipad doesn't try to update the visuals during param sweep
# #Remove superfluous columns
# @heli.hook
# def saveCSV(data, model):
# 	for c in data:
# 		if 'urban' in c or c in ['city', 'hsum'] or 'utility' in c or 'moveRate' in c or 'Unnamed' in c or 'pctile' in c:
# 			del data[c]
# 	print('Finished at', len(data))
# 	return data
#
# #Set up parameter sweep
# folder = 'CSVs'
# heli.param('csv', folder+'/malthusian')
# @heli.hook('modelPreSetup', prioritize=True)
# def turnOffCity(model): model.param('city', False)
# heli.param('stopafter', 'end3')
# results = heli.paramSweep(['rent', 'fixed'])
#
# #Post-sweep analysis
# import os, pandas
# times = [{e.name: e.triggered for e in run.events} for run in results]
# files = [f for f in os.listdir(folder) if '.csv' in f]
# analysis = []
# i=0
# for f in files:
# 	data = pandas.read_csv(folder+'/'+f)
#
# 	#Summary statistics
# 	analysis.append({
# 		'rent': data['rent'][0],
# 		'fixed': data['fixed'][0],
# 		'h': mean(data['ruralH'][-burnout:]),
# 		'pop': mean(data['ruralPop'][-burnout:])/popfactor
# 	}|times[i])
# 	i+=1
#
# analysis = pandas.DataFrame(analysis)
# analysis.to_csv(folder+'/analysis.csv')