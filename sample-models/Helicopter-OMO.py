# A model of the relative price effects of monetary shocks via helicopter drop vs. by open market operations.
# Includes a banking system to distribute OMOs. Requires the basic Helicopter.py in the same folder.
# Download the paper at https://ssrn.com/abstract=2545488

from numpy import isnan, mean, array #, std
from Helicopter import * #Building on the basic Helicopter model
heli = setup()

#===============
# BANK CLASS
#===============

# baseAgent.overdraft = 'continue-warn'
class Bank(baseAgent):
	def __init__(self, breed, id, model):
		super().__init__(breed, id, model)

		self.i = .1				#Per-period interest rate
		self.targetRR = 0.25
		self.inflation = 0
		self.accounts = {}		#Liabilities
		self.credit = {}		#Assets

		self.dif = 0			#How much credit was rationed
		self.defaultTotal = 0
		self.pLast = 50 		#Initial price level, equal to average of initial prices

	def account(self, customer):
		return self.accounts[customer.id] if customer.id in self.accounts else 0

	def setupAccount(self, customer):
		if customer.id in self.accounts: return False		#If you already have an account
		self.accounts[customer.id] = 0						#Liabilities
		self.credit[customer.id] = Loan(customer, self)		#Assets

	#Assets and liabilities should return the same thing
	#Any difference gets disbursed as interest on deposits
	@property
	def assets(self):
		return self.stocks[self.model.goods.money] + sum(l.owe for l in self.credit.values()) #Reserves

	@property
	def liabilities(self):
		return sum(list(self.accounts.values())) #Values returns a dict_values object, not a list. So wrap it in list()

	@property
	def loans(self):
		return self.assets - self.stocks[self.model.goods.money]

	@property
	def reserveRatio(self):
		l = self.liabilities
		if l == 0: return 1
		else: return self.stocks[self.model.goods.money] / l

	@property
	def realInterest(self): return self.i - self.inflation

	#amt<0 to withdraw
	def deposit(self, customer, amt):
		amt = customer.pay(self, amt)
		self.accounts[customer.id] += amt	#Credit account
		return amt

	def transfer(self, customer, recipient, amt):
		if self.accounts[customer.id] < amt: amt = self.accounts[customer.id]
		self.accounts[customer.id] -= amt
		self.accounts[recipient.id] += amt
		return amt

	def borrow(self, customer, amt):
		if amt < 0.01: return 0 #Skip blanks and float errors
		l = self.credit[customer.id]

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

		self.accounts[customer.id] += amt	#Increase liabilities
		return amt							#How much you actually borrowed

	#Returns the amount you actually pay – the lesser of amt or your outstanding balance
	def amortize(self, customer, amt):
		if amt < 0.001: return 0			#Skip blanks and float errors
		l = self.credit[customer.id]	#Your loan object
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

		self.accounts[customer.id] -= (amt - leftover)	#Reduce liabilities
		return amt - leftover							#How much you amortized

	def step(self, stage):
		for l in self.credit.values(): l.step()

		#Pay interest on deposits
		lia = self.liabilities
		profit = self.assets - lia
		if profit > self.model.param('num_agent'):
			print('Disbursing profit of $',profit)
			for id, a in self.accounts.items():
				self.accounts[id] += profit/lia * a

		#Calculate inflation as the unweighted average price change over all goods
		if self.model.t >= 2:
			inflation = self.model.cb.P/self.pLast - 1
			self.pLast = self.model.cb.P	#Remember the price from this period before altering it for the next period
			self.inflation = (19 * self.inflation + inflation) / 20		#Decaying average

		#Set interest rate and/or minimum repayment schedule
		#Count potential borrowing in the interest rate adjustment
		targeti = self.i * self.targetRR / (self.reserveRatio)

		#Adjust in proportion to the rate of reserve change
		#Positive deltaReserves indicates falling reserves; negative deltaReserves rising inventory
		if self.model.t > 2:
			deltaReserves = (self.lastReserves - self.stocks[self.model.goods.money])/self.model.cb.P
			targeti *= (1 + deltaReserves/(20 ** self.model.param('pSmooth')))
		self.i = (self.i * 24 + targeti)/25										#Interest rate stickiness

		self.lastReserves = self.stocks[self.model.goods.money]

		#Upper and lower interest rate bounds
		self.i = min(self.i, 1+self.inflation)		#interest rate cap at 100%
		self.i = max(self.i, self.inflation+0.005)	#no negative real rates
		self.i = max(self.i, 0.005)					#no negative nominal rates

class Loan():
	def __init__(self, customer, bank):
		self.customer = customer
		self.bank = bank
		self.loans = []
		self.amortizeAmt = 0

	@property
	def owe(self): return sum([l['amount'] for l in self.loans])

	def step(self):
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
			if amtz > self.bank.accounts[self.customer.id]:	#Can't charge them more than they have in the bank
				defaulted = True
				amtz = self.bank.accounts[self.customer.id]
				# print(self.bank.model.t, ': Agent', self.customer.id, 'defaulted $', self.owe - amtz)
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

#===============
# CONFIGURATION
#===============

heli.agents.addPrimitive('bank', Bank, dflt=1, priority=1, hidden=True)
heli.name = 'Helicopter/OMO'

#Disable the irrelevant checkboxes if the banking model isn't selected
#Callback for the dist parameter
@heli.hook('terminate') #Reset the disabled checkmarks when terminating a model
def bankChecks(model, val=None):
	nobank = model.param('dist')!='omo'
	model.param('num_bank', 0 if nobank else 1)
	for i in ['debt', 'rr', 'i']:
		model.params['plots'].element.disabled(i, nobank)
	for e in model.params['liqPref'].elements.values():
		e.config(state='disabled' if nobank else 'normal')

heli.hooks.add('CpanelPostInit', lambda cpanel: bankChecks(cpanel.model))	#Set the disabled checkmarks on initialization

# UPDATE CALLBACKS

def lpUpdater(model, var, breed, val):
	if model.hasModel:
		for a in model.agents['agent']:
			if a.breed == breed: a.liqPref = val

heli.params['dist'].opts = {
	'prop': 'Helicopter/Proportional',
	'lump': 'Helicopter/Lump Sum',
	'omo': 'Open Market Operation'
}
#Since the param callback takes different parameters than the GUI callback
heli.params['dist'].callback = lambda model, var, val: bankChecks(model, val)
heli.param('dist','omo')

heli.params.add('liqPref', 'Demand for Liquidity', 'slider', per='breed', dflt={'hobbit': 0.1, 'dwarf': 0.3}, opts={'low':0, 'high': 1, 'step': 0.01}, prim='agent', callback=lpUpdater, desc='The proportion of the agent\'s balances he desires to keep in cash')

heli.visual.addPlot('debt', 'Debt', selected=False)
heli.visual.addPlot('rr', 'Reserve Ratio', selected=False)
heli.visual.addPlot('i', 'Interest Rate', selected=False)

#================
# AGENT BEHAVIOR
#================

#
# General
#

#Don't bother keeping track of the bank-specific variables unless the banking system is there
#Do this here rather than at the beginning so we can decide at runtime

def cashdemand(model):
	return model.data.agentReporter('stocks', good=model.goods.money, stat='sum', prim='agent')(model)/model.data.agentReporter('balance', stat='sum', prim='agent')(model)

@heli.hook
def modelPreSetup(model):
	if model.param('num_bank') > 0:
		model.data.addReporter('defaults', model.data.agentReporter('defaultTotal', 'bank'))
		model.data.addReporter('debt', model.data.agentReporter('loans', 'bank'))
		model.data.addReporter('reserveRatio', model.data.agentReporter('reserveRatio', 'bank'))
		model.data.addReporter('targetRR', model.data.agentReporter('targetRR', 'bank'))
		model.data.addReporter('i', model.data.agentReporter('i', 'bank'))
		model.data.addReporter('r', model.data.agentReporter('realInterest', 'bank'))
		model.data.addReporter('cashdemand', cashdemand)
		model.data.addReporter('inflation', model.data.agentReporter('inflation', 'bank'))
		model.data.addReporter('M2', lambda model: model.cb.M2)

		model.visual['money'].addSeries('defaults', 'Defaults', '#CC0000')
		model.visual['money'].addSeries('M2', 'Money Supply', '#000000')
		model.visual['debt'].addSeries('debt', 'Outstanding Debt', '#000000')
		model.visual['rr'].addSeries('targetRR', 'Target', '#777777')
		model.visual['rr'].addSeries('reserveRatio', 'Reserve Ratio', '#000000')
		model.visual['i'].addSeries('i', 'Nominal interest', '#000000')
		model.visual['i'].addSeries('r', 'Real interest', '#0000CC')
		model.visual['i'].addSeries('inflation', 'Inflation', '#CC0000')
		model.visual['i'].addSeries('cashdemand', '% cash held', '#00CC00')

@heli.hook
def modelPostSetup(model):
	if hasattr(model.agents['store'][0], 'bank'):
		model.agents['store'][0].pavg = 0
		model.agents['store'][0].projects = []
		model.agents['store'][0].defaults = 0

@heli.hook
def storeStep(agent, model, stage):
	#Intertemporal transactions
	if hasattr(agent, 'bank') and model.t > 0:
		#Stipulate some demand for credit, we can worry about microfoundations later
		agent.bank.amortize(agent, agent.bank.credit[agent.id].owe/1.5) #Pay back 2/3 of the outstanding balance each period
		agent.bank.borrow(agent, model.cb.ngdp * (1-agent.bank.i)) #Borrow some amount rising in sales volume and declining in the interest rate

#
# Agents
#

#Choose a bank if necessary
@heli.hook
def baseAgentInit(agent, model):
	if model.param('num_bank') > 0 and agent.primitive != 'bank':
		agent.bank = model.agents['bank'][0]
		agent.bank.setupAccount(agent)

@heli.hook
def agentInit(agent, model):
	if model.param('num_bank') > 0:
		agent.liqPref = model.param(('liqPref', 'breed', agent.breed, 'agent'))

@heli.hook
def agentStep(agent, model, stage):
	#Deposit cash in the bank at the end of each period
	if hasattr(agent, 'bank'):
		tCash = agent.liqPref * (1/(1+agent.bank.i)) * agent.balance #Slightly interest-elastic
		agent.bank.deposit(agent, agent.stocks[agent.model.goods.money]-tCash)

#Use the bank if the bank exists
@heli.hook
def buy(agent, partner, good, q, p):
	if hasattr(agent, 'bank'):
		bal = agent.bank.account(agent)
		if p*q > bal:
			amount = bal
			leftover = (p*q - bal)/q
		else:
			amount = p*q
			leftover = 0
		agent.bank.transfer(agent, partner, amount)
		return (q, leftover)

#Use the bank if the bank exists
@heli.hook
def pay(agent, recipient, amount, model):
	if hasattr(agent, 'bank') and recipient.primitive != 'bank' and agent.primitive != 'bank':
		bal = agent.bank.account(agent)
		if amount > bal: #If there are not enough funds
			trans = bal
			amount -= bal
		else:
			trans = amount
			amount = 0
		agent.bank.transfer(agent, recipient, trans)
		return amount #Should be zero. Anything leftover gets paid in cash

@heli.hook
def checkBalance(agent, balance, model):
	if hasattr(agent, 'bank') and agent.primitive != 'bank':
		balance += agent.bank.account(agent)
		return balance

#
# Central Bank
#

def cbstep(self):
	#Record macroeconomic vars at the end of the last stage
	#Getting demand has it lagged one period…
	self.ngdp = sum(self.model.data.getLast('demand-'+good) * self.model.agents['store'][0].price[good] for good in self.model.goods.nonmonetary)
	if not self.ngdpAvg: self.ngdpAvg = self.ngdp
	self.ngdpAvg = (2 * self.ngdpAvg + self.ngdp) / 3

	#Set macroeconomic targets
	expand = 0
	if self.ngdpTarget: expand = self.ngdpTarget - self.ngdpAvg
	if self.model.param('num_bank') > 0: expand *= self.model.agents['bank'][0].reserveRatio
	if expand != 0: self.expand(expand)
CentralBank.step = cbstep

def expand(self, amount):

	#Deposit with each bank in proportion to their liabilities
	if 'bank' in self.model.agents and self.model.param('num_bank') > 0:
		self.stocks[self.model.goods.money] += amount
		self.model.agents['bank'][0].deposit(self, amount) #Budget constraint taken care of in .pay()

	elif self.model.param('dist') == 'lump':
		amt = amount/self.model.param('num_agent')
		for a in self.model.agents['agent']:
			a.stocks[self.model.goods.money] += amt
	else:
		M0 = self.M0
		for a in self.model.agents.all:
			a.stocks[self.model.goods.money] += a.stocks[self.model.goods.money]/M0 * amount
CentralBank.expand = expand

def M2(self):
	if 'bank' not in self.model.agents or self.model.param('num_bank') == 0: return self.M0
	return sum(a.balance for a in self.model.agents.all)
CentralBank.M2 = property(M2)

#Price level
#Average good prices at each store, then average all of those together weighted by the store's sale volume
#Figure out whether to break this out or not
def cbP(self):
	# denom = 0
	# numer = 0
	if not 'store' in self.model.agents: return None
	return mean(array(list(self.model.agents['store'][0].price.values())))
	# for s in self.model.agents['store']:
	# 	volume = sum(list(s.lastDemand.values()))
	# 	numer += mean(array(list(s.price.values()))) * volume
	# 	denom += volume
	#
	# if denom==0: return 1
	# else: return numer/denom
CentralBank.P = property(cbP)

heli.launchCpanel()