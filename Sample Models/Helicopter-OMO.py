# For instructions on how to run, see https://cameronharwick.com/running-a-python-abm/
# Download the paper at https://ssrn.com/abstract=2545488
# 
# #Differences from the NetLogo version:
# -Target inventory calculated as 1.5 std dev above the mean demand of the last 50 periods
# -Banking model exists and is somewhat stable
# -Code is refactored to make it simple to add agent classes
# -Demand for real balances is mediated through a CES utility function rather than being stipulated ad hoc
#
#TODO: Interface for system shocks?
#TODO: Use multiprocessing to run the graphing in a different process (and/or convert to Java)

from collections import namedtuple
import pandas

from model import Helipad
from math import sqrt
from agent import * #Necessary for callback to figure out if is instance of Agent
heli = Helipad()

#========
# THE BANK PRIMITIVE
#========

#Have to specify this first for it to be available…
class Bank():
	def __init__(self, breed, id, model):
		self.breed = breed
		self.unique_id = id
		self.model = model
		self.dead = False
		
		self.reserves = 0
		self.i = .1				#Per-period interest rate
		self.targetRR = 0.25
		self.lastWithdrawal = 0
		self.inflation = 0
		self.accounts = {}		#Liabilities
		self.credit = {}		#Assets
		
		self.model.doHooks('bankInit', [self, model])
		
			
	def balance(self, customer):
		if customer.unique_id in self.accounts: return self.accounts[customer.unique_id]
		else: return 0
	
	def setupAccount(self, customer):
		if customer.unique_id in self.accounts: return False		#If you already have an account
		self.accounts[customer.unique_id] = 0						#Liabilities
		self.credit[customer.unique_id] = Loan(customer, self)		#Assets
	
	#Assets and liabilities should return the same thing
	#Any difference gets disbursed as interest on deposits
	@property
	def assets(self):
		a = self.reserves
		for uid, l in self.credit.items():
			a += l.owe
		return a
	
	@property
	def liabilities(self):
		return sum(list(self.accounts.values())) #Values returns a dict_values object, not a list. So wrap it in list()
	
	@property
	def loans(self):
		return self.assets - self.reserves
	
	@property
	def reserveRatio(self):
		l = self.liabilities
		if l == 0: return 1
		else: return self.reserves / l
		
	@property
	def realInterest(self):
		return self.i - self.inflation
	
	@realInterest.setter
	def realInterest(self, value):
		self.i = value + self.inflation
	
	def deposit(self, customer, amt):
		if amt == 0: return 0
		if -amt > self.reserves: amt = 0.1 - self.reserves
		# print('Reserves are $', self.reserves)
		# if self.reserves > 0: print("Expanding" if amt>0 else "Contracting","by $",abs(amt),"which is ",abs(amt)/self.reserves*100,"% of reserves")
		
		if amt > customer.cash: amt = customer.cash
		customer.cash -= amt						#Charge customer
		self.reserves += amt						#Deposit cash
		self.accounts[customer.unique_id] += amt	#Credit account
		
		# print('Now reserves are $',self.reserves)
		
		return amt
	
	def withdraw(self, customer, amt):
		self.deposit(customer, -amt)
		self.lastWithdrawal += amt
	
	def transfer(self, customer, recipient, amt):		
		if self.accounts[customer.unique_id] < amt: amt = self.accounts[customer.unique_id]
		self.accounts[customer.unique_id] -= amt
		self.accounts[recipient.unique_id] += amt
		return amt
	
	def borrow(self, customer, amt):
		if amt < 0.01: return 0 #Skip blanks and float errors
		l = self.credit[customer.unique_id]
				
		#Refinance anything with a higher interest rate
		for n,loan in enumerate(l.loans):
			if loan['i'] >= self.i:
				amt += loan['amount']
				del l.loans[n]
				
		#Increase assets
		l.loans.append({
			'amount': amt,
			'i': self.i
		})
		
		self.accounts[customer.unique_id] += amt	#Increase liabilities
		
		return amt									#How much you actually borrowed
	
	#Returns the amount you actually pay – the lesser of amt or your outstanding balance
	def amortize(self, customer, amt):
		if amt < 0.001: return 0			#Skip blanks and float errors
		l = self.credit[customer.unique_id]	#Your loan object
		l.amortizeAmt += amt				#Count it toward minimum repayment
		leftover = amt
			
		#Reduce assets; amortize in the order borrowed
		while leftover > 0 and len(l.loans) > 0:
			if leftover >= l.loans[0]['amount']:
				leftover -= l.loans[0]['amount']
				del l.loans[0]
			else:
				l.loans[0]['amount'] -= leftover
				leftover = 0
			
		self.accounts[customer.unique_id] -= (amt - leftover)	#Reduce liabilities
		
		return amt - leftover									#How much you amortized
	
	def step(self, stage):
		self.lastWithdrawal = 0
		for l in self.credit: self.credit[l].step(stage)
				
		self.model.doHooks('bankStep', [self, self.model, stage])
	
	def die(self):
		self.model.agents['bank'].remove(self)
		self.model.doHooks('bankDie', [self])
		self.dead = True

class Loan():
	def __init__(self, customer, bank):
		self.customer = customer
		self.bank = bank
		self.model = bank.model
		self.loans = []
		self.amortizeAmt = 0
		self.model.doHooks('loanInit', [self, customer])
	
	@property
	def owe(self):
		amt = 0
		for l in self.loans: amt += l['amount']
		return amt
	
	def step(self, stage):
		#Charge the minimum repayment if the agent hasn't already amortized more than that amount
		minRepay = 0
		for l in self.loans:
			iLoan = l['amount'] * l['i']
			minRepay += iLoan				#You have to pay at least the interest each period
			l['amount'] += iLoan			#Roll over the remainder at the original interest rate
		
		#If they haven't paid the minimum this period, charge it
		amtz = minRepay - self.amortizeAmt
		defaulted = False
		if amtz > 0:
			if amtz > self.bank.accounts[self.customer.unique_id]:	#Can't charge them more than they have in the bank
				defaulted = True
				amtz = self.bank.accounts[self.customer.unique_id]
				# print(self.model.t, ': Agent', self.customer.unique_id, 'defaulted $', self.owe - amtz)
			self.bank.amortize(self.customer, amtz)
			if defaulted:
				for n, l in enumerate(self.loans):
					self.loans[n]['amount'] /= 2
					self.bank.defaultTotal += l['amount']/2
					##Cap defaults at the loan amount. Otherwise if i>1, defaulting results in negative debt
					# if l['i'] >= 1:
					# 	self.bank.defaultTotal += l['amount']
					# 	del self.loans[n]
					# else:
					# 	l['amount'] -= l['amount'] * l['i']
					# 	self.bank.defaultTotal += l['amount'] * l['i']
				
		self.amortizeAmt = 0
		self.model.doHooks('loanStep', [self, self.model, stage])

#===============
# CONFIGURATION
#===============

heli.addPrimitive('bank', Bank, dflt=1, low=0, high=10, priority=1)
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

#Disable the irrelevant checkboxes if the banking model isn't selected
#Callback for the dist parameter
def bankChecks(gui, val=None):
	nobank = gui.model.param('dist')!='omo'
	gui.model.param('agents_bank', 0 if nobank else 1)
	for i in ['debt', 'rr', 'i']:
		gui.checks[i].set(False)
		gui.checks[i].disabled(nobank)

#Since the param callback takes different parameters than the GUI callback
def bankCheckWrapper(model, var, val):
	bankChecks(model.gui, val)

heli.addHook('terminate', bankChecks)		#Reset the disabled checkmarks when terminating a model
heli.addHook('GUIPostInit', bankChecks)	#Set the disabled checkmarks on initialization

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
	'prop': 'Helicopter/Proportional',
	'lump': 'Helicopter/Lump Sum',
	'omo': 'Open Market Operation'
}, runtime=False, callback=bankCheckWrapper)

heli.params['agents_bank'][1]['type'] = 'hidden'
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
heli.addPlot('debt', 'Debt')
heli.addPlot('rr', 'Reserve Ratio')
heli.addPlot('i', 'Interest Rate')

heli.defaultPlots.append('rbal')
heli.addSeries('capital', lambda: 1/len(heli.primitives['agent']['breeds']), '', 'CCCCCC')
for breed, d in heli.primitives['agent']['breeds'].items():
	heli.data.addReporter('rbalDemand-'+breed, rbaltodemand(breed))
	heli.data.addReporter('eCons-'+breed, heli.data.agentReporter('expCons', 'agent', breed=breed, stat='sum'))
	# heli.data.addReporter('rWage-'+breed, lambda model: heli.data.agentReporter('wage', 'store')(model) / heli.data.agentReporter('price', 'store', narrow=b.good)(model))
	# heli.data.addReporter('expWage', heli.data.agentReporter('expWage', 'agent'))
	heli.data.addReporter('rBal-'+breed, heli.data.agentReporter('realBalances', 'agent', breed=breed))
	heli.data.addReporter('shortage-'+AgentGoods[breed], heli.data.agentReporter('lastShortage', 'store', narrow=AgentGoods[breed]))
	heli.data.addReporter('invTarget-'+AgentGoods[breed], heli.data.agentReporter('invTarget', 'store', narrow=AgentGoods[breed]))
	heli.data.addReporter('portion-'+AgentGoods[breed], heli.data.agentReporter('portion', 'store', narrow=AgentGoods[breed]))
	
	heli.addSeries('demand', 'eCons-'+breed, breed.title()+'s\' Expected Consumption', d.color2)
	heli.addSeries('shortage', 'shortage-'+AgentGoods[breed], AgentGoods[breed].title()+' Shortage', heli.goods[AgentGoods[breed]].color)
	heli.addSeries('rbal', 'rbalDemand-'+breed, breed.title()+' Target Balances', d.color2)
	heli.addSeries('rbal', 'rBal-'+breed, breed.title()+ 'Real Balances', d.color)
	heli.addSeries('inventory', 'invTarget-'+AgentGoods[breed], AgentGoods[breed].title()+' Inventory Target', heli.goods[AgentGoods[breed]].color2)
	heli.addSeries('capital', 'portion-'+AgentGoods[breed], AgentGoods[breed].title()+' Capital', heli.goods[AgentGoods[breed]].color)
	# heli.addSeries('Wage', 'expWage', 'Expected Wage', '999999')

heli.data.addReporter('storeCash', heli.data.agentReporter('balance', 'store'))
heli.data.addReporter('StoreCashDemand', heli.data.agentReporter('cashDemand', 'store'))
heli.addSeries('money', 'StoreCashDemand', 'Store Cash Demand', 'CCCCCC')
heli.data.addReporter('wage', heli.data.agentReporter('wage', 'store'))
heli.addSeries('wage', 'wage', 'Wage', '000000')

#================
# AGENT BEHAVIOR
#================

#
# General
#

#Don't bother keeping track of the bank-specific variables unless the banking system is there
#Do this here rather than at the beginning so we can decide at runtime
def modelPreSetup(model):
	if 'bank' in model.primitives and model.param('agents_bank') > 0:
		model.data.addReporter('defaults', model.data.agentReporter('defaultTotal', 'bank'))
		model.data.addReporter('debt', model.data.agentReporter('loans', 'bank'))
		model.data.addReporter('reserveRatio', model.data.agentReporter('reserveRatio', 'bank'))
		model.data.addReporter('targetRR', model.data.agentReporter('targetRR', 'bank'))
		model.data.addReporter('i', model.data.agentReporter('i', 'bank'))
		model.data.addReporter('r', model.data.agentReporter('realInterest', 'bank'))
		model.data.addReporter('inflation', model.data.agentReporter('inflation', 'bank'))
		model.data.addReporter('withdrawals', model.data.agentReporter('lastWithdrawal', 'bank'))
		model.data.addReporter('M2', model.data.cbReporter('M2'))

		model.addSeries('money', 'defaults', 'Defaults', 'CC0000')
		model.addSeries('money', 'M2', 'Money Supply', '000000')
		model.addSeries('debt', 'debt', 'Outstanding Debt', '000000')
		model.addSeries('rr', 'targetRR', 'Target', '777777')
		model.addSeries('rr', 'reserveRatio', 'Reserve Ratio', '000000')
		model.addSeries('i', 'i', 'Nominal interest', '000000')
		model.addSeries('i', 'r', 'Real interest', '0000CC')
		model.addSeries('i', 'inflation', 'Inflation', 'CC0000')
heli.addHook('modelPreSetup', modelPreSetup)

#
# Agents
#

from agent import CES

#Choose a bank if necessary
def moneyUserInit(agent, model):
	if model.param('agents_bank') > 0:
		agent.bank = choice(model.agents['bank'])
		agent.bank.setupAccount(agent)
heli.addHook('moneyUserInit', moneyUserInit)

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
	agent.utils = agent.utility.calculate({'good': bought, 'rbal': agent.cash/itemPrice}) if hasattr(agent,'utility') else 0	#Consume goods & get utility
	
	negadjust = q - bought											#Update your consumption expectations if the store has a shortage
	if negadjust > basicq: negadjust = basicq
	agent.expCons = (19 * agent.expCons + basicq-negadjust)/20		#Set expected consumption as a decaying average of consumption history
	
	#Deposit cash in the bank at the end of each period
	if hasattr(agent, 'bank'):
		agent.bank.deposit(agent, agent.cash)
heli.addHook('agentStep', agentStep)

def realBalances(agent):
	if not hasattr(agent, 'store'): return 0
	return agent.balance/agent.store.price[agent.item] #Cheating here to assume a single store...
	# return agent.balance/agent.model.cb.P
Agent.realBalances = property(realBalances)

#Use the bank if the bank exists
def pay(agent, recipient, amount, model):
	if hasattr(agent, 'bank'):
		bal = agent.bank.balance(agent)
		# origamt = amount
		if amount > bal: #If there are not enough funds
			trans = bal
			amount -= bal
		else:
			trans = amount
			amount = 0
		agent.bank.transfer(agent, recipient, trans)
		return amount #Should be zero. Anything leftover gets paid in cash
heli.addHook('pay', pay)

def checkBalance(agent, balance, model):
	if hasattr(agent, 'bank'):
		bal += agent.bank.balance(agent)
		return bal

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
	
	if hasattr(store, 'bank'):
		store.pavg = 0
		store.projects = []
		store.defaults = 0
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
		#Wage shocks (give them something to smooth with the banking system)
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
	
	#Intertemporal transactions
	if hasattr(store, 'bank') and model.t > 0:
		#Ok, just stipulate some demand for credit, we'll worry about microfoundations later
		store.bank.amortize(store, store.bank.credit[store.unique_id].owe/1.5)
		store.bank.borrow(store, store.model.cb.ngdp * (1-store.bank.i))
		
		# store.pavg = (model.cb.P + 2*store.pavg)/3	#Relatively short rolling average price level
		# expRRev = model.cb.ngdp/store.pavg			#Since the store's nominal revenue is NGDP
		#
		# #Borrow in real terms, since—with a constant money supply—nominal borrowing will never be viable except at zero interest
		# #Generate an investment opportunity
		# prodinc = random.normal(1.5, 0.5)	# % increase in productivity
		# if prodinc < 0: prodinc = 0
		# time = int(random.normal(20, 5))	# Expected periods until completion
		# if time < 1: time = 1
		# cost = random.normal(5,2)			#Expected cost as a percentage of expected revenue/period
		# if cost < 0.1: cost = 0.1
		# cost = 0.01*cost*expRRev
		#
		# #Calculate expected present value
		# r = store.bank.i - store.bank.inflation
		# pval = 1/(1+r)**time * (0.01*prodinc*expRRev/r)
		#
		# #Borrow the money
		# if pval > cost:
		# 	print('Borrowing $',cost,'for present value is',pval,', r is',r)
		# 	store.bank.borrow(store, cost)
		# 	store.projects.append({
		# 		'prodinc': prodinc,
		# 		'amt': cost*expRRev,
		# 		'exprrev': expRRev,
		# 		'end': store.model.t + time,
		# 		'completed': False
		# 	})
		# else: print('Did not borrow. Cost is',cost,', present value is',pval,', r is',r)
		#
		# amortized = 0
		# for p in store.projects:
		#
		# 	#Pay back previous projects out of new earnings
		# 	if expRRev > p['exprrev'] + amortized/store.model.cb.P:
		# 		amt = (expRRev - p['exprrev'])*store.model.cb.P - amortized	#Nominal
		# 		if amt > p['amt']: amt = p['amt']
		# 		print('Amortizing $',amt)
		# 		store.bank.amortize(store, amt)
		# 		p['amt'] -= amt
		# 		amortized += amt/store.model.cb.P
		#
		# 	#Realize investment projects and increase productivity
		# 	if not p['completed'] and store.model.t >= p['end']-1 and random.randint(0,100) < 25:
		# 		print('Completing project, increasing productivity by',p['prodinc'],'%')
		# 		for g in store.price:
		# 			store.model.goodParam('prod', g, store.model.goodParam('prod',g)*(1+p['prodinc']))
		# 		p['completed'] = True
		#
		# 	#Default if it takes more than 20 periods past the expected date to pay back
		# 	if store.model.t > p['end']+20:
		# 		print('Defaulting $',p['amt'])
		# 		store.defaults += p['amt']
		# 		store.projects.remove(p)
		#
		# 	#Remove if paid off and completed
		# 	if p['completed'] and p['amt'] <= 0:
		# 		print('Project completed and paid off')
		# 		store.projects.remove(p)
			
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
		if model.param('agents_bank') > 0: expand *= mean([b.reserveRatio for b in model.agents['bank']])
		if expand != 0: cb.expand(expand)
heli.addHook('cbStep', cbStep)

#
# Bank
#

def bankInit(bank, model):
	bank.dif = 0			#How much credit was rationed
	bank.defaultTotal = 0
	bank.pLast = 50 		#Initial price level, equal to average of initial prices
heli.addHook('bankInit', bankInit)

def bankStep(bank, model, stage):
	#Pay interest on deposits
	lia = bank.liabilities
	profit = bank.assets - lia
	if profit > model.param('agents_agent'):
		print('Disbursing profit of $',profit)
		for id, a in bank.accounts.items():
			bank.accounts[id] += profit/lia * a
		
	# #Set target reserve ratio
	# wd = model.data.getLast('withdrawals', 50)
	# mn, st = wd.mean(), wd.std()
	# if isnan(mn) or isnan(st): mn, st = .1, .1
	# ttargetRR = (mn + 2 * st) / lia
	# bank.targetRR = (bank.targetRR + 49*ttargetRR)/50
	
	#Calculate inflation as the unweighted average price change over all goods
	if model.t >= 2:
		inflation = model.cb.P/bank.pLast - 1
		bank.pLast = model.cb.P	#Remember the price from this period before altering it for the next period
		bank.inflation = (19 * bank.inflation + inflation) / 20		#Decaying average
	
	#Set interest rate and/or minimum repayment schedule
	#Count potential borrowing in the interest rate adjustment
	targeti = bank.i * bank.targetRR / (bank.reserveRatio)
	
	#Adjust in proportion to the rate of reserve change
	#Positive deltaReserves indicates falling reserves; negative deltaReserves rising inventory
	if model.t > 2:
		deltaReserves = (bank.lastReserves - bank.reserves)/model.cb.P
		targeti *= (1 + deltaReserves/(20 ** model.param('pSmooth')))
	bank.i = (bank.i * 24 + targeti)/25										#Interest rate stickiness
	
	bank.lastReserves = bank.reserves
			
	#Upper and lower interest rate bounds
	if bank.i > 1 + bank.inflation: bank.i = 1 + bank.inflation				#interest rate cap at 100%
	if bank.i < bank.inflation + 0.005: bank.i = bank.inflation + 0.005		#no negative real rates
	if bank.i < 0.005: bank.i = 0.005										#no negative nominal rates
	
heli.addHook('bankStep', bankStep)

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