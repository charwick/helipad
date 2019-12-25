# ==========
# Logic for the agents, store, and bank
# Do not run this file; import model.py and run from your file.
# ==========

from random import choice
from numpy import *
from utility import *

#Everybody who uses money, in this case all agents including the store and bank
class MoneyUser():
	def __init__(self, id, model):
		self.unique_id = int(id)
		self.model = model
		self.cash = 0
		self.dead = False
		
		self.model.doHooks('moneyUserInit', [self, self.model])
	
	def step(self, stage):
		self.model.doHooks('moneyUserStep', [self, self.model, stage])
	
	def pay(self, recipient, amount):
		if amount > self.balance: amount = self.balance #Budget constraint
		amount_ = self.model.doHooks('pay', [self, recipient, amount, self.model])
		if amount_ is not None: amount = amount_
				
		if amount > 0:
			recipient.cash += amount
			self.cash -= amount
	
	def die(self):
		self.model.doHooks('moneyUserDie', [self])
		self.dead = True
	
	@property		#Nominal
	def balance(self):
		bal = self.cash
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_
		
		return bal
		
#Customers
class Agent(MoneyUser):
	def __init__(self, breed, id, model):
		super().__init__(id, model)
		
		self.breed = breed
		if model.param('M0'):
			self.cash = model.param('M0')/model.param('agents_agent')	#Initial cash endowment
		self.chooseStore()
		
		self.age = 0
		self.utils = 0
		self.parent = None
		
		self.model.doHooks('agentInit', [self, model])
	
	def step(self, stage):
		super().step(stage)
		if hasattr(self, 'store') and self.store.dead: self.chooseStore()	
		self.model.doHooks('agentStep', [self, self.model, stage])
		self.age += 1
	
	#Function assigning an agent to a store
	#The agentChooseStore filter should assign a Store object to the agent's 'store' property
	def chooseStore(self):
		self.model.doHooks('agentChooseStore', [self, self.model, self.model.agents['store']])
	
	def reproduce(self, funcs={}):
		maxid = 0
		for a in self.model.agents['agent']:
			if a.unique_id > maxid:
				maxid = a.unique_id
		newagent = Agent(self.breed, maxid+1, self.model)
		
		#Copy all writeable parameters and update those specified in the funcs argument
		params = [a for a in dir(self) if not (a.startswith('__') or callable(getattr(self,a)))]
		for param in params:
			if param == 'utility': continue #Do something less hackish here to make sure objects don't get copied...
			val = getattr(self, param)
			if param in funcs:
				if (callable(funcs[param])): newval = funcs[param](val)
				else:
					if isinstance(funcs[param], tuple): funcs[param], scale = funcs[param]
					else: scale = 'linear'
						
					if scale=='log': newval = random.lognormal(log(val), funcs[param])
					else: newval = random.normal(val, funcs[param])
			else: newval = val
			try: setattr(newagent, param, newval)
			except: pass	#skip @properties
		
		newagent.unique_id = maxid+1
		newagent.parent = self
		self.model.agents['agent'].append(newagent)
		self.model.param('agents_agent', self.model.param('agents_agent')+1)
		
		self.model.doHooks('agentReproduce', [self, newagent, self.model])
	
	def die(self):
		self.model.agents['agent'].remove(self)
		self.model.param('agents_agent', self.model.param('agents_agent')-1)
		self.model.doHooks('agentDie', [self])
		super().die()
	
	@property
	def debt(self):
		if not 'bank' in self.model.primitives or self.model.param('agents_bank') == 0: return 0
		return self.bank.credit[self.unique_id].owe

class Store(MoneyUser):
	
	def __init__(self, breed, id, model):
		super().__init__(id, model)
		
		self.breed = breed
		self.price = {}
		self.inventory = {}
		self.lastDemand = {}		#Aggregate effective demand for each good, not including shortages
		
		for good in model.goods:
			self.price[good] = 50
			self.inventory[good] = 0
			self.lastDemand[good] = 0
		
		self.model.doHooks('storeInit', [self, model])
	
	def step(self, stage):
		super().step(stage)
		self.model.doHooks('storeStep', [self, self.model, stage])
	
	#Returns the quantity actually sold
	#Which is the same as quantity input, unless there's a shortage
	def buyFrom(self, item, quantity):
		self.model.doHooks('storePreBuy', [self, item, quantity])
		
		if quantity < 0: quantity = 0
		if quantity > self.inventory[item]:
			q = self.inventory[item]
			self.lastShortage[item] += quantity - q
			self.inventory[item] = 0
		
		else:
			self.inventory[item] -= quantity
			q = quantity
		
		self.lastDemand[item] += q
		# self.cash += self.price[item] * q
		
		self.model.doHooks('storePostBuy', [self, item, q])
		return q
	
	def die(self):
		self.model.agents['store'].remove(self)
		self.model.doHooks('storeDie', [self])
		super().die()

class CentralBank(MoneyUser):
	ngdpAvg = 0
	inflation = 0		#Target. so 0.005 would be 0.5%
	ngdp = 0
	
	def __init__(self, id, model):
		super().__init__(id, model)
		self.unique_id = id
		self.model = model
		
		self.model.doHooks('cbInit', [self, model])
	
	def step(self, stage):
		
		#Record macroeconomic vars at the end of the last stage
		if stage == self.model.stages:
			self.ngdp = 0
			for good in self.model.goods:
				for s in self.model.agents['store']:
					self.ngdp += s.price[good] * s.lastDemand[good]
			if not self.ngdpAvg: self.ngdpAvg = self.ngdp
			self.ngdpAvg = (2 * self.ngdpAvg + self.ngdp) / 3
		
		self.model.doHooks('cbStep', [self, self.model, stage])
	
	def expand(self, amount):
		
		#Deposit with each bank in proportion to their liabilities
		if 'bank' in self.model.primitives and self.model.param('agents_bank') > 0:
			self.cash += amount
			denom = 0
			for b in self.model.agents['bank']:
				denom += b.liabilities
			for b in self.model.agents['bank']:
				r = b.reserves
				a = amount * b.liabilities/denom
				if -a > r: a = -r + 1
				b.deposit(self, a)
				
		elif self.model.param('dist') == 'lump':
			amt = amount/self.model.param('agents_agent')
			for a in self.model.agents['agent']:
				a.cash += amt
		else:
			M0 = self.M0
			for a in self.model.agents['agent']:
				a.cash += a.cash/M0 * amount
		
			for s in self.model.agents['store']:
				s.cash += s.cash/M0 * amount
		
		#Update model parameter, bypassing the param() function
		self.model.params['M0'][0] = self.M0
				
	@property
	def M0(self):
		total = 0
		for s in self.model.agents['store']: total += s.cash
		for a in self.model.agents['agent']: total += a.cash
		if 'bank' in self.model.primitives and self.model.param('agents_bank') > 0: total += self.bank.reserves
		return total
	
	@M0.setter
	def M0(self, value):
		self.expand(value - self.M0)
	
	@property
	def M2(self):
		if 'bank' not in self.model.primitives or self.model.param('agents_bank') == 0: return self.M0
	
		total = self.bank.reserves
		for a in self.model.agents['agent']: total += a.balance
		for s in self.model.agents['store']: total += s.balance
		return total
	
	#Price level
	#Average good prices at each store, then average all of those together weighted by the store's sale volume
	@property
	def P(self):
		denom = 0
		numer = 0
		for s in self.model.agents['store']:
			volume = sum(list(s.lastDemand.values()))
			numer += mean(array(list(s.price.values()))) * volume
			denom += volume
		
		if denom==0: return 1
		else: return numer/denom

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