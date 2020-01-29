# For instructions on how to run, see https://cameronharwick.com/running-a-python-abm/
# Download the paper at https://ssrn.com/abstract=2545488
# 
# #Differences from the NetLogo version:
# -Target inventory calculated as 1.5 std dev above the mean demand of the last 50 periods
# -Code is refactored to make it simple to add agent classes
# -Demand for real balances is mediated through a CES utility function rather than being stipulated ad hoc
#
#TODO: Interface for system shocks?
#TODO: Use multiprocessing to run the graphing in a different process (and/or convert to Java)

from collections import namedtuple
from itertools import combinations
from colour import Color
import pandas

from model import Helipad
from math import sqrt
from agent import * #Necessary for callback to figure out if is instance of Agent
heli = Helipad()

#===============
# CONFIGURATION
#===============

heli.addPrimitive('store', Store, dflt=1, low=0, high=10, priority=2)
heli.addPrimitive('agent', Agent, dflt=50, low=1, high=100, priority=3)

# Configure how many breeds there are and what good each consumes
# In this model, goods and breeds correspond, but they don't necessarily have to
breeds = [
	('hobbit', 'jam', 'D73229'),
	('dwarf', 'axe', '2D8DBE'),
	# ('orc', 'flesh', '664411'),
	# ('elf', 'lembas', 'CCBB22')
]
AgentGoods = {}
for b in breeds:
	heli.addBreed(b[0], b[2], prim='agent')
	heli.addGood(b[1], b[2])
	AgentGoods[b[0]] = b[1] #Hang on to this list for future looping

heli.order = 'random'

# UPDATE CALLBACKS

def storeUpdater(model, var, val):
	if model.hasModel:
		for s in model.agents['store']:
			setattr(s, var, val)

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

heli.params['agents_store'][1]['type'] = 'hidden'

heli.addParameter('pSmooth', 'Price Smoothness', 'slider', dflt=1.5, opts={'low': 1, 'high': 3, 'step': 0.05}, callback=storeUpdater)
heli.addParameter('wStick', 'Wage Stickiness', 'slider', dflt=10, opts={'low': 1, 'high': 50, 'step': 1}, callback=storeUpdater)
heli.addParameter('kImmob', 'Capital Immobility', 'slider', dflt=100, opts={'low': 1, 'high': 150, 'step': 1}, callback=storeUpdater)
#Low Es means the two are complements (0=perfect complements)
#High Es means the two are substitutes (infinity=perfect substitutes)
#Doesn't really affect anything though – even utility – so don't bother exposing it
heli.addParameter('sigma', 'Elast. of substitution', 'hidden', dflt=.5, opts={'low': 0, 'high': 10, 'step': 0.1})

heli.addBreedParam('rbd', 'Demand for Real Balances', 'slider', dflt={'hobbit':7, 'dwarf': 35}, opts={'low':1, 'high': 50, 'step': 1}, prim='agent', callback=rbalUpdater)
heli.addGoodParam('prod', 'Productivity', 'slider', dflt=1.75, opts={'low':0.1, 'high': 2, 'step': 0.1}) #If you shock productivity, make sure to call rbalupdater

#Takes as input the slider value, outputs b_g. See equation (A8) in the paper.
def rbaltodemand(breed):
	def reporter(model):
		rbd = model.breedParam('rbd', breed, prim='agent')
		beta = rbd/(1+rbd)
		
		return (beta/(1-beta)) * len(model.goods) * sqrt(model.goodParam('prod',AgentGoods[breed])) / sum([1/sqrt(pr) for pr in model.goodParam('prod').values()])

	return reporter

#Data Collection
heli.addPlot('shortage', 'Shortages', 3)
heli.addPlot('rbal', 'Real Balances', 5)
heli.addPlot('capital', 'Production', 9)
heli.addPlot('wage', 'Wage', 11)
heli.addSeries('capital', lambda: 1/len(heli.primitives['agent']['breeds']), '', 'CCCCCC')
for breed, d in heli.primitives['agent']['breeds'].items():
	heli.data.addReporter('rbalDemand-'+breed, rbaltodemand(breed))
	heli.data.addReporter('eCons-'+breed, heli.data.agentReporter('expCons', 'agent', breed=breed, stat='sum'))
	# heli.data.addReporter('rWage-'+breed, lambda model: heli.data.agentReporter('wage', 'store')(model) / heli.data.agentReporter('price', 'store', good=b.good)(model))
	# heli.data.addReporter('expWage', heli.data.agentReporter('expWage', 'agent'))
	heli.data.addReporter('rBal-'+breed, heli.data.agentReporter('realBalances', 'agent', breed=breed))
	heli.data.addReporter('shortage-'+AgentGoods[breed], heli.data.agentReporter('lastShortage', 'store', good=AgentGoods[breed]))
	heli.data.addReporter('invTarget-'+AgentGoods[breed], heli.data.agentReporter('invTarget', 'store', good=AgentGoods[breed]))
	heli.data.addReporter('portion-'+AgentGoods[breed], heli.data.agentReporter('portion', 'store', good=AgentGoods[breed]))
	
	heli.addSeries('demand', 'eCons-'+breed, breed.title()+'s\' Expected Consumption', d.color2)
	heli.addSeries('shortage', 'shortage-'+AgentGoods[breed], AgentGoods[breed].title()+' Shortage', heli.goods[AgentGoods[breed]].color)
	heli.addSeries('rbal', 'rbalDemand-'+breed, breed.title()+' Target Balances', d.color2)
	heli.addSeries('rbal', 'rBal-'+breed, breed.title()+ 'Real Balances', d.color)
	heli.addSeries('inventory', 'invTarget-'+AgentGoods[breed], AgentGoods[breed].title()+' Inventory Target', heli.goods[AgentGoods[breed]].color2)
	heli.addSeries('capital', 'portion-'+AgentGoods[breed], AgentGoods[breed].title()+' Capital', heli.goods[AgentGoods[breed]].color)
	# heli.addSeries('Wage', 'expWage', 'Expected Wage', '999999')

#Price ratio plots
def ratioReporter(item1, item2):
	def reporter(model):
		return model.data.agentReporter('price', 'store', good=item1)(model)/model.data.agentReporter('price', 'store', good=item2)(model)
	return reporter
heli.addPlot('ratios', 'Price Ratios', position=3, logscale=True)
heli.addSeries('ratios', lambda: 1, '', 'CCCCCC')	#plots ratio of 1 for reference without recording a column of ones
for r in combinations(heli.goods.keys(), 2):
	heli.data.addReporter('ratio-'+r[0]+'-'+r[1], ratioReporter(r[0], r[1]))
	c1, c2 = heli.goods[r[0]].color, heli.goods[r[1]].color
	c3 = Color(red=(c1.red+c2.red)/2, green=(c1.green+c2.green)/2, blue=(c1.blue+c2.blue)/2)
	heli.addSeries('ratios', 'ratio-'+r[0]+'-'+r[1], r[0].title()+'/'+r[1].title()+' Ratio', c3)
heli.defaultPlots.extend(['rbal', 'ratios'])

#Misc plots
heli.data.addReporter('storeCash', heli.data.agentReporter('balance', 'store'))
heli.addSeries('money', 'storeCash', 'Store Cash', '777777')
heli.data.addReporter('StoreCashDemand', heli.data.agentReporter('cashDemand', 'store'))
heli.addSeries('money', 'StoreCashDemand', 'Store Cash Demand', 'CCCCCC')
heli.data.addReporter('wage', heli.data.agentReporter('wage', 'store'))
heli.addSeries('wage', 'wage', 'Wage', '000000')

#================
# AGENT BEHAVIOR
#================

#
# Agents
#

from agent import CES

def agentInit(agent, model):
	agent.store = choice(model.agents['store'])
	agent.item = AgentGoods[agent.breed]
	rbd = model.breedParam('rbd', agent.breed, prim='agent')
	beta = rbd/(rbd+1)
	agent.utility = CES(['good','rbal'], agent.model.param('sigma'), {'good': 1-beta, 'rbal': beta })
	
	agent.expRWage = 100
	agent.prevBal = agent.cash
	agent.expCons = model.goodParam('prod', agent.item)
	
	#Set to equilibrium value based on parameters. Not strictly necessary but avoids the burn-in period.
	agent.cash = model.agents['store'][0].price[AgentGoods[agent.breed]] * rbaltodemand(agent.breed)(model)
	
heli.addHook('agentInit', agentInit)

def agentStep(agent, model, stage):
	itemPrice = agent.store.price[agent.item]
	
	b = agent.balance/itemPrice		#Real balances
	q = agent.utility.demand(agent.balance, {'good': itemPrice, 'rbal': itemPrice})['good']	#Equimarginal condition given CES between real balances and consumption
	basicq = q						#Save this for later since we adjust q
	
	bought = agent.store.buyFrom(agent.item, q)
	agent.pay(agent.store, bought * itemPrice)
	if agent.cash < 0: agent.cash = 0							#Floating point error gives you infinitessimaly negative cash sometimes
	agent.utils = agent.utility.calculate({'good': bought, 'rbal': agent.balance/itemPrice}) if hasattr(agent,'utility') else 0	#Consume goods & get utility
	
	negadjust = q - bought											#Update your consumption expectations if the store has a shortage
	if negadjust > basicq: negadjust = basicq
	agent.expCons = (19 * agent.expCons + basicq-negadjust)/20		#Set expected consumption as a decaying average of consumption history
	
heli.addHook('agentStep', agentStep)

def realBalances(agent):
	if not hasattr(agent, 'store'): return 0
	return agent.balance/agent.store.price[agent.item] #Cheating here to assume a single store...
	# return agent.balance/agent.model.cb.P
Agent.realBalances = property(realBalances)

#
# Store
#

def storeInit(store, model):
	store.invTarget = {}		#Inventory targets in terms of absolute quantity
	store.lastShortage = {}
	store.portion = {}			#Allocation of capital to the various goods
	store.wage = 0
	store.cashDemand = 0
	
	for good in model.goods:
		store.portion[good] = 1/len(model.goods)
		store.invTarget[good] = 1
		store.lastShortage[good] = 0
		
		#Start with equilibrium prices. Not strictly necessary, but it eliminates the burn-in period.
		store.price[good] = (model.param('M0')/model.param('agents_agent')) * sum([1/sqrt(model.goodParam('prod',g)) for g in model.goods])/(sqrt(model.goodParam('prod',good))*(len(model.goods)+sum([1+model.breedParam('rbd', b, prim='agent') for b in model.primitives['agent']['breeds']])))

heli.addHook('storeInit', storeInit)

def storeStep(store, model, stage):
	N = model.param('agents_agent')
		
	#Calculate wages
	bal = store.balance
	store.cashDemand = N * store.wage #Hold enough cash for one period's disbursements
	newwage = (bal - store.cashDemand) / N
	if newwage < 1: newwage = 1
	store.wage = (store.wage * model.param('wStick') + newwage)/(1 + model.param('wStick'))
	if store.wage * N > bal: store.wage = bal / N 	#Budget constraint
	
	#Hire labor
	labor, tPrice = 0, 0
	for a in model.agents['agent']:
		if not isinstance(a, Agent): continue
		
		#Pay agents
		#Wage shocks
		if store.wage < 0: store.wage = 0
		wage = random.normal(store.wage, store.wage/2 + 0.1)	#Can't have zero stdev
		wage = 0 if wage < 0 else wage							#Wage bounded from below by 0
		store.pay(a, wage)
		labor += 1
		
		a.lastRWage = wage/store.price[a.item]
		a.expRWage = (19 * a.expRWage + a.lastRWage)/20		#Expected real wage, decaying average
		
	for good in model.goods: tPrice += store.price[good] #Sum of prices. This is a separate loop because we need it in order to do this calculation
	avg, stdev = {},{} #Hang onto these for use with credit calculations
	for i in model.goods:

		#Keep track of typical demand
		#Target sufficient inventory to handle 1.5 standard deviations above mean demand for the last 50 periods
		history = pandas.Series(model.data.getLast('demand-'+i, 50)) + pandas.Series(model.data.getLast('shortage-'+i, 50))
		avg[i], stdev[i] = history.mean(), history.std()
		itt = (1 if isnan(avg[i]) else avg[i]) + 1.5 * (1 if isnan(stdev[i]) else stdev[i])
		store.invTarget[i] = (store.invTarget[i] + itt)/2 #Smooth it a bit
		
		#Set prices
		#Change in the direction of hitting the inventory target
		# store.price[i] += log(store.invTarget[i] / (store.inventory[i][0] + store.lastShortage[i])) #Jim's pricing rule?
		store.price[i] += (store.invTarget[i] - store.inventory[i] + store.lastShortage[i])/100 #/150
		
		#Adjust in proportion to the rate of inventory change
		#Positive deltaInv indicates falling inventory; negative deltaInv rising inventory
		lasti = model.data.getLast('inv-'+i,2)[0] if model.t > 1 else 0
		deltaInv = lasti - store.inventory[i]
		store.price[i] *= (1 + deltaInv/(50 ** model.param('pSmooth')))
		if store.price[i] < 0: store.price[i] = 1
		
		#Produce stuff
		store.portion[i] = (model.param('kImmob') * store.portion[i] + store.price[i]/tPrice) / (model.param('kImmob') + 1)	#Calculate capital allocation
		store.inventory[i] = store.inventory[i] + store.portion[i] * labor * model.goodParam('prod',i)
			
heli.addHook('storeStep', storeStep)

#
# Central Bank
#

def cbInit(cb, model):
	cb.ngdpTarget = False if not model.param('ngdpTarget') else 10000
heli.addHook('cbInit', cbInit)

def cbStep(cb, model, stage):
	#Set macroeconomic targets at the end of the last stage
	if stage == model.stages:
		expand = 0
		if cb.inflation: expand = M0(model) * cb.inflation
		if cb.ngdpTarget: expand = cb.ngdpTarget - cb.ngdpAvg
		if expand != 0: cb.expand(expand)
heli.addHook('cbStep', cbStep)

def modelPostStep(model):
	#Reset per-period variables
	#Can't replace these with getLast because these are what feed into getLast
	#Put this after the intertemporal transactions since that needs lastDemand
	for s in model.agents['store']:
		for i in model.goods:
			s.lastDemand[i] = 0
			s.lastShortage[i] = 0
heli.addHook('modelPostStep', modelPostStep)

#========
# SHOCKS
#========

#Timer functions

#With n% probability each period
def shock_randn(n):
	def fn(t): return True if random.randint(0,100) < n else False
	return fn
	
#Once at t=n
#n can be an int or a list of periods
def shock_atperiodn(n):
	def fn(t):
		if type(n) == list:
			return True if t in n else False
		else:
			return True if t==n else False
	return fn
	
#Regularly every n periods
def shock_everyn(n):
	def fn(t): return True if t%n==0 else False
	return fn

#Shock functions

#Random shock to dwarf cash demand
def shock(v):
	c = random.normal(v, 4)
	return c if c >= 1 else 1
heli.registerShock('Dwarf real balances', 'rbd', shock, shock_randn(2), paramType='breed', obj='dwarf', prim='agent')

#Shock the money supply
def mshock(v):
	# return v*2
	pct = random.normal(1, 15)
	m = v * (1+pct/100)
	if m < 10000: m = 10000		#Things get weird when there's a money shortage
	return m
heli.registerShock('M0 (2% prob)', 'M0', mshock, shock_randn(2), desc="Shocks the money supply a random percentage (µ=1, σ=15) with 2% probability each period")
# heli.registerShock('M0 (every 700 periods)', 'M0', mshock, shock_everyn(700))

heli.launchGUI()