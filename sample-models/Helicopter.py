# A model of the relative price effects of monetary shocks via helicopter drop
# Download the paper at https://ssrn.com/abstract=2545488

#To generate IRFs, turn off the visualization, turn on stopafter, and one shock.

from itertools import combinations
from math import sqrt
from helipad import *
from numpy import random, isnan

M0 = 120000

#===============
# STORE CLASS
# Has to come before adding the primitive
#===============

class Store(baseAgent):
	def __init__(self, breed, id, model):
		super().__init__(breed, id, model)

		#Start with equilibrium prices. Not strictly necessary, but it eliminates the burn-in period. See eq. A7
		sm=sum(1/sqrt(model.param(('prod','good',g))) for g in model.goods.nonmonetary) * M0/(model.param('num_agent')*(len(model.goods.nonmonetary)+sum(1+model.param(('rbd','breed',b,'agent')) for b in model.agents['agent'].breeds)))
		self.price = {g:sm/(sqrt(model.param(('prod','good',g)))) for g in model.goods.nonmonetary}

		self.invTarget = {g:model.param(('prod','good',g))*model.param('num_agent')*2 for g in model.goods.nonmonetary}
		self.portion = {g:1/(len(model.goods.nonmonetary)) for g in model.goods.nonmonetary} #Capital allocation
		self.wage = 0
		self.cashDemand = 0

	def step(self, stage):
		super().step(stage)
		N = self.model.param('num_agent')

		#Calculate wages
		self.cashDemand = N * self.wage #Hold enough cash for one period's disbursements
		newwage = (self.balance - self.cashDemand) / N
		newwage = max(newwage, 1)
		self.wage = (self.wage * self.model.param('wStick') + newwage)/(1 + self.model.param('wStick'))
		if self.wage * N > self.balance: self.wage = self.balance / N 	#Budget constraint

		#Hire labor, with individualized wage shocks
		labor = 0
		for a in self.model.agents['agent']:
			self.wage = max(self.wage, 0)
			wage = random.normal(self.wage, self.wage/2 + 0.1)	#Can't have zero stdev
			wage = max(wage, 0)									#Wage bounded from below by 0
			self.pay(a, wage)
			labor += 1

		tPrice = sum(self.price[good] for good in self.model.goods.nonmonetary)
		avg, stdev = {},{} #Hang onto these for use with credit calculations
		for i in self.model.goods.nonmonetary:

			#Just have a fixed inventory target, but update if params do
			self.invTarget = {g:self.model.param(('prod','good',g))*self.model.param('num_agent')*2 for g in self.model.goods.nonmonetary}

			#Produce stuff
			self.portion[i] = (self.model.param('kImmob') * self.portion[i] + self.price[i]/tPrice) / (self.model.param('kImmob') + 1)	#Calculate capital allocation
			self.stocks[i] = self.stocks[i] + self.portion[i] * labor * self.model.param(('prod', 'good', i))

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

#===============
# CONFIGURATION
#===============

#Stick this here so we can build on it with the OMO model
def setup():
	heli = Helipad()
	heli.agents.addPrimitive('store', Store, dflt=1, priority=2, hidden=True)

	# Configure how many breeds there are and what good each consumes
	# In this model, goods and breeds correspond, but they don't necessarily have to
	breeds = [
		('hobbit', 'jam', '#D73229'),
		('dwarf', 'axe', '#2D8DBE'),
		# ('elf', 'lembas', '#CCBB22')
	]
	AgentGoods = {}
	for b in breeds:
		heli.agents.addBreed(b[0], b[2], prim='agent')
		heli.goods.add(b[1], b[2])
		AgentGoods[b[0]] = b[1] #Hang on to this list for future looping
	heli.goods.add('cash', '#009900', money=True)

	heli.name = 'Helicopter'
	heli.agents.order = 'random'

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

	heli.params.add('ngdpTarget', 'NGDP Target', 'check', dflt=False, callback=ngdpUpdater)
	heli.params.add('dist', 'Distribution', 'menu', dflt='prop', opts={
		'prop': 'Proportional',
		'lump': 'Lump Sum'
	}, runtime=False)

	heli.params.add('pSmooth', 'Price Smoothness', 'slider', dflt=1.5, opts={'low': 1, 'high': 3, 'step': 0.05})
	heli.params.add('wStick', 'Wage Stickiness', 'slider', dflt=10, opts={'low': 1, 'high': 50, 'step': 1})
	heli.params.add('kImmob', 'Capital Immobility', 'slider', dflt=100, opts={'low': 1, 'high': 150, 'step': 1})
	heli.params.group('Environment', ('pSmooth', 'wStick', 'kImmob'), opened=False)

	#Low Es means the two are complements (0=perfect complements)
	#High Es means the two are substitutes (infinity=perfect substitutes)
	#Doesn't really affect anything though – even utility – so don't bother exposing it
	heli.params.add('sigma', 'Elast. of substitution', 'hidden', dflt=.5, opts={'low': 0, 'high': 10, 'step': 0.1})

	heli.params.add('rbd', 'Demand for Real Balances', 'slider', per='breed', dflt={'hobbit':7, 'dwarf': 35}, opts={'low':1, 'high': 50, 'step': 1}, prim='agent', callback=rbalUpdater)
	heli.params.add('prod', 'Productivity', 'slider', per='good', dflt=1.75, opts={'low':0.1, 'high': 2, 'step': 0.1}) #If you shock productivity, make sure to call rbalupdater

	#Takes as input the slider value, outputs b_g. See equation (A8) in the paper.
	def rbaltodemand(breed):
		def reporter(model):
			rbd = model.param(('rbd', 'breed', breed, 'agent'))
			beta = rbd/(1+rbd)

			return (beta/(1-beta)) * len(model.goods) * sqrt(model.param(('prod','good',AgentGoods[breed]))) / sum(1/sqrt(pr) for pr in model.param(('prod','good')).values())

		return reporter

#===============
# DATA COLLECTION AND VISUALIZATION
#===============

	from helipad.visualize import TimeSeries
	viz = heli.useVisual(TimeSeries)
	viz.dim = (1000, 800)
	viz.pos = (400, 100)

	viz.addPlot('prices', 'Prices', 1, selected=True)
	viz.addPlot('inventory', 'Inventory', 3)
	viz.addPlot('rbal', 'Real Balances', 5)
	viz.addPlot('ngdp', 'NGDP', 7, selected=False)
	viz.addPlot('capital', 'Production', 9, selected=False)
	viz.addPlot('wage', 'Wage', 11, selected=False)
	viz.addPlot('shortage', 'Shortages', 6, selected=False)

	viz['capital'].addSeries(lambda t: 1/len(heli.agents['agent'].breeds), '', '#CCCCCC')

	# heli.data.addReporter('rBal', heli.data.agentReporter('realBalances', 'agent', breed=True))
	def shortageReporter(good):
		def reporter(model): return model.shortages[good]
		return reporter

	for breed, d in heli.agents['agent'].breeds.items():
		heli.data.addReporter('rbalDemand-'+breed, rbaltodemand(breed))
		heli.data.addReporter('shortage-'+AgentGoods[breed], shortageReporter(AgentGoods[breed]))
		heli.data.addReporter('eCons-'+breed, heli.data.agentReporter('expCons', 'agent', breed=breed, stat='sum'))
		# heli.data.addReporter('rWage-'+breed, lambda model: heli.data.agentReporter('wage', 'store')(model) / heli.data.agentReporter('price', 'store', good=b.good)(model))
		# heli.data.addReporter('expWage', heli.data.agentReporter('expWage', 'agent'))
		heli.data.addReporter('rBal-'+breed, heli.data.agentReporter('realBalances', 'agent', breed=breed))
		heli.data.addReporter('invTarget-'+AgentGoods[breed], heli.data.agentReporter('invTarget', 'store', good=AgentGoods[breed]))
		heli.data.addReporter('portion-'+AgentGoods[breed], heli.data.agentReporter('portion', 'store', good=AgentGoods[breed]))

		viz['demand'].addSeries('eCons-'+breed, breed.title()+'s\' Expected Consumption', d.color2)
		viz['shortage'].addSeries('shortage-'+AgentGoods[breed], AgentGoods[breed].title()+' Shortage', d.color)
		viz['rbal'].addSeries('rbalDemand-'+breed, breed.title()+' Target Balances', d.color2)
		viz['rbal'].addSeries('rBal-'+breed, breed.title()+ 'Real Balances', d.color)
		viz['inventory'].addSeries('invTarget-'+AgentGoods[breed], AgentGoods[breed].title()+' Inventory Target', heli.goods[AgentGoods[breed]].color2)
		viz['capital'].addSeries('portion-'+AgentGoods[breed], AgentGoods[breed].title()+' Capital', heli.goods[AgentGoods[breed]].color)
		# viz['wage'].addSeries('expWage', 'Expected Wage', '#999999')

	#Do this one separately so it draws on top
	for good, g in heli.goods.nonmonetary.items():
		heli.data.addReporter('inv-'+good, heli.data.agentReporter('stocks', 'store', good=good))
		viz['inventory'].addSeries('inv-'+good, good.title()+' Inventory', g.color)
		heli.data.addReporter('price-'+good, heli.data.agentReporter('price', 'store', good=good))
		viz['prices'].addSeries('price-'+good, good.title()+' Price', g.color)

	#Price ratio plots
	def ratioReporter(item1, item2):
		def reporter(model):
			return model.data.agentReporter('price', 'store', good=item1)(model)/model.data.agentReporter('price', 'store', good=item2)(model)
		return reporter
	viz.addPlot('ratios', 'Price Ratios', position=3, logscale=True)
	viz['ratios'].addSeries(lambda t: 1, '', '#CCCCCC')	#plots ratio of 1 for reference without recording a column of ones

	for r in combinations(heli.goods.nonmonetary.keys(), 2):
		heli.data.addReporter('ratio-'+r[0]+'-'+r[1], ratioReporter(r[0], r[1]))
		c1, c2 = heli.goods[r[0]].color, heli.goods[r[1]].color
		viz['ratios'].addSeries('ratio-'+r[0]+'-'+r[1], r[0].title()+'/'+r[1].title()+' Ratio', c1.blend(c2))

	#Misc plots
	heli.data.addReporter('ngdp', lambda model: model.cb.ngdp)
	viz['ngdp'].addSeries('ngdp', 'NGDP', '#000000')
	heli.data.addReporter('storeCash', heli.data.agentReporter('balance', 'store'))
	viz['money'].addSeries('storeCash', 'Store Cash', '#777777')
	heli.data.addReporter('StoreCashDemand', heli.data.agentReporter('cashDemand', 'store'))
	viz['money'].addSeries('StoreCashDemand', 'Store Cash Demand', '#CCCCCC')
	heli.data.addReporter('wage', heli.data.agentReporter('wage', 'store'))
	viz['wage'].addSeries('wage', 'Wage', '#000000')

#================
# POST-ANALYSIS
# Generate the appropriate impulse response functions
#================

	@heli.hook
	def terminate(model, data):
		shocks = model.params['shocks'].get()
		if not model.param('stopafter') or not shocks: return

		from statsmodels.tsa.api import VAR
		import matplotlib.pyplot as plt

		if 'Dwarf' in shocks[0]:	#Equilibrating shocks
			data = data[['M0', 'ratio-jam-axe', 'rBal-dwarf']]
		elif 'M0' in shocks[0]:		#Disequilibrating shocks
			data = data[['M0', 'ratio-jam-axe']]

		model = VAR(data)
		results = model.fit(50)
		irf = results.irf(50)
		irf.plot(orth=False, impulse='M0', response='ratio-jam-axe')
		plt.show(block=False)

#================
# AGENT BEHAVIOR
#================

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
		agent.stocks[model.goods.money] = agent.store.price[agent.item] * rbaltodemand(agent.breed)(heli)

	@heli.hook
	def agentStep(agent, model, stage):
		itemPrice = agent.store.price[agent.item]

		q = agent.utility.demand(agent.balance, {'good': itemPrice, 'rbal': itemPrice})['good']	#Equimarginal condition given CES between real balances and consumption
		basicq = q						#Save this for later since we adjust q
		bought = agent.buy(agent.store, agent.item, q, itemPrice)
		if bought < q: model.shortages[agent.item] += q-bought #Record shortages
		if agent.stocks[model.goods.money] < 0: agent.stocks[model.goods.money] = 0	#Floating point error gives infinitessimaly negative cash sometimes
		agent.utils = agent.utility.calculate({'good': agent.stocks[agent.item], 'rbal': agent.balance/itemPrice}) if hasattr(agent,'utility') else 0	#Get utility
		agent.stocks[agent.item] = 0 #Consume goods

		negadjust = q - bought											#Update your consumption expectations if the store has a shortage
		negadjust = min(negadjust, basicq)
		agent.expCons = (19 * agent.expCons + basicq-negadjust)/20		#Set expected consumption as a decaying average of consumption history

	def realBalances(agent):
		if not hasattr(agent, 'store'): return 0
		return agent.balance/agent.store.price[agent.item]
		# return agent.balance/agent.model.cb.P
	Agent.realBalances = property(realBalances)

	@heli.hook
	def modelPreStep(model):
		model.shortages = {g:0 for g in model.goods.nonmonetary}

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
	heli.shocks.add('Dwarf real balances', ('rbd','breed','dwarf','agent'), shock, heli.shocks.randn(2), active=False)

	#Shock the money supply
	def mshock(model):
		pct = random.normal(3, 15) #High mean to counteract the downward bias of (1-%)(1+%)
		m = model.cb.M0 * (1+pct/100)
		m = max(m, 10000)		#Things get weird when there's a money shortage
		model.cb.M0 = m
	heli.shocks.add('M0 (2% prob)', None, mshock, heli.shocks.randn(2), desc="Shocks the money supply a random percentage (µ=1, σ=15) with 2% probability each period")

	#Only one shock at a time
	def shocksCallback(model, var, val):
		shocks = heli.param('shocks')
		if len(shocks) > 1:
			for s in shocks:
				if s != val[0]:
					model.shocks[s].active(False)

		if 'M0' in val[0] and val[1]: model.param('ngdpTarget', False)
		elif 'Dwarf' in val[0] and val[1]: model.param('ngdpTarget', True)
	heli.params['shocks'].callback = shocksCallback

	return heli

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
		self.stocks[self.model.goods.money] = M0 #Has to have assets in order to contract

		self.ngdpTarget = False if not model.param('ngdpTarget') else 10000

	def step(self):

		#Record macroeconomic vars at the end of the last stage
		#Getting demand has it lagged one period…
		self.ngdp = sum(self.model.data.getLast('demand-'+good) * self.model.agents['store'][0].price[good] for good in self.model.goods.nonmonetary)
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
				a.stocks[self.model.goods.money] += amt
		else:
			M0 = self.M0
			for a in self.model.agents.all:
				a.stocks[self.model.goods.money] += a.stocks[self.model.goods.money]/M0 * amount

	@property
	def M0(self):
		return self.model.data.agentReporter('stocks', 'all', good=self.model.goods.money, stat='sum')(self.model)

	@M0.setter
	def M0(self, value): self.expand(value - self.M0)

#Only launch the cpanel if we haven't embedded
if __name__ == '__main__':
	heli = setup()
	heli.launchCpanel()