# A model of the relative price effects of monetary shocks via helicopter drop
# Download the paper at https://ssrn.com/abstract=2545488

from itertools import combinations
import pandas

from helipad import *
from math import sqrt
heli = Helipad()

#===============
# STORE CLASS
# Has to come before adding the primitive
#===============

class Store(baseAgent):
	def __init__(self, breed, id, model):
		super().__init__(breed, id, model)
		
		#Start with equilibrium prices. Not strictly necessary, but it eliminates the burn-in period. See eq. A7
		sm=sum([1/sqrt(model.param(('prod','good',g))) for g in model.nonMoneyGoods]) * M0/(model.param('num_agent')*(len(model.nonMoneyGoods)+sum([1+model.param(('rbd','breed',b,'agent')) for b in model.primitives['agent'].breeds])))
		self.price = {g:sm/(sqrt(model.param(('prod','good',g)))) for g in model.nonMoneyGoods}
		
		self.invTarget = {g:model.param(('prod','good',g))*model.param('num_agent') for g in model.nonMoneyGoods}
		self.portion = {g:1/(len(model.nonMoneyGoods)) for g in model.nonMoneyGoods} #Capital allocation
		self.wage = 0
		self.cashDemand = 0
	
	def step(self, stage):
		super().step(stage)
		N = self.model.param('num_agent')
		
		#Calculate wages
		self.cashDemand = N * self.wage #Hold enough cash for one period's disbursements
		newwage = (self.balance - self.cashDemand) / N
		if newwage < 1: newwage = 1
		self.wage = (self.wage * self.model.param('wStick') + newwage)/(1 + self.model.param('wStick'))
		if self.wage * N > self.balance: self.wage = self.balance / N 	#Budget constraint
	
		#Hire labor, with individualized wage shocks
		labor = 0
		for a in self.model.agents['agent']:
			if self.wage < 0: self.wage = 0
			wage = random.normal(self.wage, self.wage/2 + 0.1)	#Can't have zero stdev
			wage = 0 if wage < 0 else wage						#Wage bounded from below by 0
			self.pay(a, wage)
			labor += 1
	
		tPrice = sum([self.price[good] for good in self.model.nonMoneyGoods])		
		avg, stdev = {},{} #Hang onto these for use with credit calculations
		for i in self.model.nonMoneyGoods:

			#Keep track of typical demand
			#Target sufficient inventory to handle 1.5 standard deviations above mean demand for the last 50 periods
			history = pandas.Series(self.model.data.getLast('demand-'+i, 50)) + pandas.Series(self.model.data.getLast('shortage-'+i, 50))
			avg[i], stdev[i] = history.mean(), history.std()
			itt = (1 if isnan(avg[i]) else avg[i]) + 1.5 * (1 if isnan(stdev[i]) else stdev[i])
			self.invTarget[i] = (self.invTarget[i] + itt)/2 #Smooth it a bit
		
			#Set prices
			#Change in the direction of hitting the inventory target
			# self.price[i] += log(self.invTarget[i] / (self.inventory[i][0] + self.lastShortage[i])) #Jim's pricing rule?
			self.price[i] += (self.invTarget[i] - self.stocks[i] + self.model.data.getLast('shortage-'+i))/100 #/150
		
			#Adjust in proportion to the rate of inventory change
			#Positive deltaInv indicates falling inventory; negative deltaInv rising inventory
			lasti = self.model.data.getLast('inv-'+i,2)[0] if self.model.t > 1 else 0
			deltaInv = lasti - self.stocks[i]
			self.price[i] *= (1 + deltaInv/(50 ** self.model.param('pSmooth')))
			if self.price[i] < 0: self.price[i] = 1
		
			#Produce stuff
			self.portion[i] = (self.model.param('kImmob') * self.portion[i] + self.price[i]/tPrice) / (self.model.param('kImmob') + 1)	#Calculate capital allocation
			self.stocks[i] = self.stocks[i] + self.portion[i] * labor * self.model.param(('prod', 'good', i))

#===============
# CONFIGURATION
#===============

heli.addPrimitive('store', Store, dflt=1, priority=2, hidden=True)
heli.addPrimitive('agent', Agent, dflt=50, low=1, high=100, priority=3)

# Configure how many breeds there are and what good each consumes
# In this model, goods and breeds correspond, but they don't necessarily have to
breeds = [
	('hobbit', 'jam', '#D73229'),
	('dwarf', 'axe', '#2D8DBE'),
	# ('elf', 'lembas', '#CCBB22')
]
AgentGoods = {}
for b in breeds:
	heli.addBreed(b[0], b[2], prim='agent')
	heli.addGood(b[1], b[2])
	AgentGoods[b[0]] = b[1] #Hang on to this list for future looping
M0 = 120000
heli.addGood('cash', '#009900', money=True)

heli.name = 'Helicopter'
heli.order = 'random'

# UPDATE CALLBACKS

def ngdpUpdater(model, var, val):
	if model.hasModel: model.cb.ngdpTarget = val if not val else model.cb.ngdp

def rbalUpdater(model, var, breed, val):
	if model.hasModel:
		beta = val/(1+val)
			
		for a in model.agents['agent']:
			if hasattr(a, 'utility') and a.breed == breed:
				a.utility.coeffs['rbal'] = beta
				a.utility.coeffs['good'] = 1-beta
				
#Set up the info for the sliders on the control panel
#These variables attach to the Helicopter object
#Each parameter requires a corresponding routine in Helicopter.updateVar()
heli.addParameter('ngdpTarget', 'NGDP Target', 'check', dflt=False, callback=ngdpUpdater)
heli.addParameter('dist', 'Distribution', 'menu', dflt='prop', opts={
	'prop': 'Proportional',
	'lump': 'Lump Sum'
}, runtime=False)

heli.addParameter('pSmooth', 'Price Smoothness', 'slider', dflt=1.5, opts={'low': 1, 'high': 3, 'step': 0.05})
heli.addParameter('wStick', 'Wage Stickiness', 'slider', dflt=10, opts={'low': 1, 'high': 50, 'step': 1})
heli.addParameter('kImmob', 'Capital Immobility', 'slider', dflt=100, opts={'low': 1, 'high': 150, 'step': 1})
#Low Es means the two are complements (0=perfect complements)
#High Es means the two are substitutes (infinity=perfect substitutes)
#Doesn't really affect anything though – even utility – so don't bother exposing it
heli.addParameter('sigma', 'Elast. of substitution', 'hidden', dflt=.5, opts={'low': 0, 'high': 10, 'step': 0.1})

heli.addBreedParam('rbd', 'Demand for Real Balances', 'slider', dflt={'hobbit':7, 'dwarf': 35}, opts={'low':1, 'high': 50, 'step': 1}, prim='agent', callback=rbalUpdater)
heli.addGoodParam('prod', 'Productivity', 'slider', dflt=1.75, opts={'low':0.1, 'high': 2, 'step': 0.1}) #If you shock productivity, make sure to call rbalupdater

#Takes as input the slider value, outputs b_g. See equation (A8) in the paper.
def rbaltodemand(breed):
	def reporter(model):
		rbd = model.param(('rbd', 'breed', breed, 'agent'))
		beta = rbd/(1+rbd)
		
		return (beta/(1-beta)) * len(model.goods) * sqrt(model.param(('prod','good',AgentGoods[breed]))) / sum([1/sqrt(pr) for pr in model.param(('prod','good')).values()])

	return reporter

#===============
# DATA COLLECTION AND VISUALIZATION
#===============

from helipad.visualize import TimeSeries
viz = heli.useVisual(TimeSeries)

viz.addPlot('prices', 'Prices', 1, selected=True)
viz.addPlot('inventory', 'Inventory', 3)
viz.addPlot('rbal', 'Real Balances', 5)
viz.addPlot('ngdp', 'NGDP', 7, selected=False)
viz.addPlot('capital', 'Production', 9, selected=False)
viz.addPlot('wage', 'Wage', 11, selected=False)
viz.plots['capital'].addSeries(lambda t: 1/len(heli.primitives['agent'].breeds), '', '#CCCCCC')

# heli.data.addReporter('rBal', heli.data.agentReporter('realBalances', 'agent', breed=True))

for breed, d in heli.primitives['agent'].breeds.items():
	heli.data.addReporter('rbalDemand-'+breed, rbaltodemand(breed))
	heli.data.addReporter('eCons-'+breed, heli.data.agentReporter('expCons', 'agent', breed=breed, stat='sum'))
	# heli.data.addReporter('rWage-'+breed, lambda model: heli.data.agentReporter('wage', 'store')(model) / heli.data.agentReporter('price', 'store', good=b.good)(model))
	# heli.data.addReporter('expWage', heli.data.agentReporter('expWage', 'agent'))
	heli.data.addReporter('rBal-'+breed, heli.data.agentReporter('realBalances', 'agent', breed=breed))
	heli.data.addReporter('invTarget-'+AgentGoods[breed], heli.data.agentReporter('invTarget', 'store', good=AgentGoods[breed]))
	heli.data.addReporter('portion-'+AgentGoods[breed], heli.data.agentReporter('portion', 'store', good=AgentGoods[breed]))
	
	viz.plots['demand'].addSeries('eCons-'+breed, breed.title()+'s\' Expected Consumption', d.color2)
	viz.plots['rbal'].addSeries('rbalDemand-'+breed, breed.title()+' Target Balances', d.color2)
	viz.plots['rbal'].addSeries('rBal-'+breed, breed.title()+ 'Real Balances', d.color)
	viz.plots['inventory'].addSeries('invTarget-'+AgentGoods[breed], AgentGoods[breed].title()+' Inventory Target', heli.goods[AgentGoods[breed]].color2)
	viz.plots['capital'].addSeries('portion-'+AgentGoods[breed], AgentGoods[breed].title()+' Capital', heli.goods[AgentGoods[breed]].color)
	# viz.plots['wage'].addSeries('expWage', 'Expected Wage', '#999999')

#Do this one separately so it draws on top
for good, g in heli.nonMoneyGoods.items():
	heli.data.addReporter('inv-'+good, heli.data.agentReporter('stocks', 'store', good=good))
	viz.plots['inventory'].addSeries('inv-'+good, good.title()+' Inventory', g.color)
	heli.data.addReporter('price-'+good, heli.data.agentReporter('price', 'store', good=good))
	viz.plots['prices'].addSeries('price-'+good, good.title()+' Price', g.color)

#Price ratio plots
def ratioReporter(item1, item2):
	def reporter(model):
		return model.data.agentReporter('price', 'store', good=item1)(model)/model.data.agentReporter('price', 'store', good=item2)(model)
	return reporter
viz.addPlot('ratios', 'Price Ratios', position=3, logscale=True)
viz.plots['ratios'].addSeries(lambda t: 1, '', '#CCCCCC')	#plots ratio of 1 for reference without recording a column of ones

for r in combinations(heli.nonMoneyGoods.keys(), 2):
	heli.data.addReporter('ratio-'+r[0]+'-'+r[1], ratioReporter(r[0], r[1]))
	c1, c2 = heli.goods[r[0]].color, heli.goods[r[1]].color
	viz.plots['ratios'].addSeries('ratio-'+r[0]+'-'+r[1], r[0].title()+'/'+r[1].title()+' Ratio', c1.blend(c2))

#Misc plots
heli.data.addReporter('ngdp', lambda model: model.cb.ngdp)
viz.plots['ngdp'].addSeries('ngdp', 'NGDP', '#000000')
heli.data.addReporter('storeCash', heli.data.agentReporter('balance', 'store'))
viz.plots['money'].addSeries('storeCash', 'Store Cash', '#777777')
heli.data.addReporter('StoreCashDemand', heli.data.agentReporter('cashDemand', 'store'))
viz.plots['money'].addSeries('StoreCashDemand', 'Store Cash Demand', '#CCCCCC')
heli.data.addReporter('wage', heli.data.agentReporter('wage', 'store'))
viz.plots['wage'].addSeries('wage', 'Wage', '#000000')

#================
# AGENT BEHAVIOR
#================

#
# Agents
#

from helipad.utility import CES

@heli.hook
def agentInit(agent, model):
	agent.store = model.agents['store'][0]
	agent.item = AgentGoods[agent.breed]
	rbd = model.param(('rbd', 'breed', agent.breed, 'agent'))
	beta = rbd/(rbd+1)
	agent.utility = CES({'good': 1-beta, 'rbal': beta }, agent.model.param('sigma'))
	agent.expCons = model.param(('prod', 'good', agent.item))
	
	#Set cash endowment to equilibrium value based on parameters. Not strictly necessary but avoids the burn-in period.
	agent.stocks[model.moneyGood] = agent.store.price[agent.item] * rbaltodemand(agent.breed)(heli)

@heli.hook
def agentStep(agent, model, stage):
	itemPrice = agent.store.price[agent.item]
	
	b = agent.balance/itemPrice		#Real balances
	q = agent.utility.demand(agent.balance, {'good': itemPrice, 'rbal': itemPrice})['good']	#Equimarginal condition given CES between real balances and consumption
	basicq = q						#Save this for later since we adjust q
	
	bought = agent.buy(agent.store, agent.item, q, itemPrice)
	if agent.stocks[model.moneyGood] < 0: agent.stocks[model.moneyGood] = 0	#Floating point error gives infinitessimaly negative cash sometimes
	agent.utils = agent.utility.calculate({'good': agent.stocks[agent.item], 'rbal': agent.balance/itemPrice}) if hasattr(agent,'utility') else 0	#Get utility
	agent.stocks[agent.item] = 0 #Consume goods
	
	negadjust = q - bought											#Update your consumption expectations if the store has a shortage
	if negadjust > basicq: negadjust = basicq
	agent.expCons = (19 * agent.expCons + basicq-negadjust)/20		#Set expected consumption as a decaying average of consumption history

def realBalances(agent):
	if not hasattr(agent, 'store'): return 0
	return agent.balance/agent.store.price[agent.item]
	# return agent.balance/agent.model.cb.P
Agent.realBalances = property(realBalances)
			
#
# Central Bank
#

class CentralBank(baseAgent):
	ngdpAvg = 0
	ngdp = 0
	primitive = 'cb'
	
	def __init__(self, id, model):
		super().__init__(None, id, model)
		self.id = id
		self.model = model
		
		self.ngdpTarget = False if not model.param('ngdpTarget') else 10000
	
	def step(self):
		
		#Record macroeconomic vars at the end of the last stage
		#Getting demand has it lagged one period…
		self.ngdp = sum([self.model.data.getLast('demand-'+good) * self.model.agents['store'][0].price[good] for good in self.model.nonMoneyGoods])
		if not self.ngdpAvg: self.ngdpAvg = self.ngdp
		self.ngdpAvg = (2 * self.ngdpAvg + self.ngdp) / 3
		
		#Set macroeconomic targets
		expand = 0
		if self.ngdpTarget: expand = self.ngdpTarget - self.ngdpAvg
		if expand != 0: self.expand(expand)
	
	def expand(self, amount):				
		if self.model.param('dist') == 'lump':
			amt = amount/self.model.param('num_agent')
			for a in self.model.agents['agent']:
				a.stocks[self.model.moneyGood] += amt
		else:
			M0 = self.M0
			for a in self.model.allagents.values():
				a.stocks[self.model.moneyGood] += a.stocks[self.model.moneyGood]/M0 * amount
				
	@property
	def M0(self):
		return self.model.data.agentReporter('stocks', 'all', good=self.model.moneyGood, stat='sum')(self.model)
	
	@M0.setter
	def M0(self, value): self.expand(value - self.M0)

@heli.hook
def modelPostSetup(model): model.cb = CentralBank(0, model)

@heli.hook
def modelPostStep(model): model.cb.step()	#Step the central bank last

#========
# SHOCKS
#========

#Random shock to dwarf cash demand
def shock(v):
	c = random.normal(v, 4)
	return c if c >= 1 else 1
heli.shocks.register('Dwarf real balances', ('rbd','breed','dwarf','agent'), shock, heli.shocks.randn(2))

#Shock the money supply
def mshock(model):
	# return v*2
	pct = random.normal(1, 15)
	m = model.cb.M0 * (1+pct/100)
	if m < 10000: m = 10000		#Things get weird when there's a money shortage
	model.cb.M0 = m
heli.shocks.register('M0 (2% prob)', None, mshock, heli.shocks.randn(2), desc="Shocks the money supply a random percentage (µ=1, σ=15) with 2% probability each period")

heli.launchCpanel()