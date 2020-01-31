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
		self.goods = {good: params.endowment(self.breed if hasattr(self, 'breed') else None) if params.endowment is not None else 0 for good,params in model.goods.items()}
		
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
		self.breed = breed
		super().__init__(id, model)

		if model.param('M0'):
			self.cash = model.param('M0')/model.param('agents_agent')	#Initial cash endowment
		
		self.age = 0
		self.utils = 0
		self.parent = None
		
		self.model.doHooks('agentInit', [self, model])
	
	def step(self, stage):
		super().step(stage)
		self.model.doHooks('agentStep', [self, self.model, stage])
		self.age += 1
	
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
		self.breed = breed
		super().__init__(id, model)
		
		self.price = {}
		self.lastDemand = {}		#Aggregate effective demand for each good, not including shortages
		
		for good in model.goods:
			self.price[good] = 50
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
		if quantity > self.goods[item]:
			q = self.goods[item]
			self.lastShortage[item] += quantity - q
			self.goods[item] = 0
		
		else:
			self.goods[item] -= quantity
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
				if 'store' in self.model.agents:
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
		for lst in self.model.agents.values():
			for a in lst:
				if hasattr(a, 'cash'): total += a.cash
				elif hasattr(a, 'reserves'): total += a.reserves
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
	#Figure out whether to break this out or not
	@property
	def P(self):
		denom = 0
		numer = 0
		if not 'store' in self.model.agents: return None
		for s in self.model.agents['store']:
			volume = sum(list(s.lastDemand.values()))
			numer += mean(array(list(s.price.values()))) * volume
			denom += volume
		
		if denom==0: return 1
		else: return numer/denom