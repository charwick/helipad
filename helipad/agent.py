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
		self.dead = False
		self.goods = {}
		for good, params in model.goods.items():
			if params.endowment is None: self.goods[good] = 0
			elif callable(params.endowment): self.goods[good] = params.endowment(self.breed if hasattr(self, 'breed') else None)
			else: self.goods[good] = params.endowment
		
		self.currentDemand = {g:0 for g in model.goods.keys()}
		self.currentShortage = {g:0 for g in model.goods.keys()}
					
		self.model.doHooks('moneyUserInit', [self, self.model])
	
	def step(self, stage):
		self.currentDemand = {g:0 for g in self.model.goods.keys()}
		self.currentShortage = {g:0 for g in self.model.goods.keys()}
		self.model.doHooks('moneyUserStep', [self, self.model, stage])
	
	#Give amt1 of good 1, get amt2 of good 2
	#Negative values of amt1 and amt2 allowed, which reverses the direction
	def trade(self, partner, good1, amt1, good2, amt2):
		self.model.doHooks('preTrade', [self, partner, good1, amt1, good2, amt2])
		
		if amt2 != 0: price = amt1 / amt2
		
		#Budget constraints. Hold price constant if hit		
		if amt1 > self.goods[good1]:
			self.currentShortage[good1] += amt1 - self.goods[good1]
			amt1 = self.goods[good1]
			if amt2 != 0: amt2 = amt1 / price
		elif -amt1 > partner.goods[good1]:
			partner.currentShortage[good1] += -amt1 - partner.goods[good1]
			amt1 = -partner.goods[good1]
			if amt2 != 0: amt2 = amt1 / price
		if amt2 > partner.goods[good2]:
			partner.currentShortage[good2] += amt1 - partner.goods[good2]
			amt2 = partner.goods[good2]
			amt1 = price * amt2
		elif -amt2 > self.goods[good2]:
			self.currentShortage[good2] += -amt1 - self.goods[good2]
			amt2 = -self.goods[good2]
			amt1 = price * amt2

		self.goods[good1] -= amt1
		partner.goods[good1] += amt1
		self.goods[good2] += amt2
		partner.goods[good2] -= amt2
		
		#Record demand
		if amt1 > 0: partner.currentDemand[good1] += amt1
		else: self.currentDemand[good1] -= amt1
		if amt2 > 0: self.currentDemand[good2] += amt2
		else: partner.currentDemand[good2] -= amt2
		
		self.model.doHooks('postTrade', [self, partner, good1, amt1, good2, amt2])
	
	#Price is per-unit
	#Returns the quantity actually sold, Which is the same as quantity input unless there's a shortage
	def buy(self, partner, good, q, p):
		if self.model.moneyGood is None: raise RuntimeError('Buy function requires a monetary good to be specified')
		qp = self.model.doHooks('buy', [self, partner, good, q, p])
		if qp is not None: q, p = qp
		
		before = self.goods[good]
		self.trade(partner, self.model.moneyGood, p*q, good, q)
		return self.goods[good] - before
	
	#Unilateral
	def pay(self, recipient, amount):
		if self.model.moneyGood is None: raise RuntimeError('Pay function requires a monetary good to be specified')
		
		if amount > self.balance: amount = self.balance #Budget constraint
		amount_ = self.model.doHooks('pay', [self, recipient, amount, self.model])
		if amount_ is not None: amount = amount_
				
		if amount > 0:
			recipient.goods[self.model.moneyGood] += amount
			self.goods[self.model.moneyGood] -= amount
	
	def die(self):
		self.model.doHooks('moneyUserDie', [self])
		self.dead = True
	
	@property
	def balance(self):
		if self.model.moneyGood is None: raise RuntimeError('Balance checking requires a monetary good to be specified')
		bal = self.goods[self.model.moneyGood]
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_
		
		return bal
		
#Customers
class Agent(MoneyUser):
	def __init__(self, breed, id, model):
		self.breed = breed
		super().__init__(id, model)
		
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
		
		self.price = {g:50 for g in model.goods}
		self.model.doHooks('storeInit', [self, model])
	
	def step(self, stage):
		super().step(stage)
		self.model.doHooks('storeStep', [self, self.model, stage])
	
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
		#Getting last demand has it lagged two periods…
		#Break this into Helicopter model
		if stage == self.model.stages:
			self.ngdp = 0
			if 'store' in self.model.agents:
				for good in self.model.goods:
					if good == self.model.moneyGood: continue
					self.ngdp += self.model.data.getLast('demand-'+good) * self.model.agents['store'][0].price[good]
				if not self.ngdpAvg: self.ngdpAvg = self.ngdp
				self.ngdpAvg = (2 * self.ngdpAvg + self.ngdp) / 3
		
		self.model.doHooks('cbStep', [self, self.model, stage])
	
	def expand(self, amount):
		
		#Deposit with each bank in proportion to their liabilities
		if 'bank' in self.model.primitives and self.model.param('agents_bank') > 0:
			self.goods[self.model.moneyGood] += amount
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
				a.goods[self.model.moneyGood] += amt
		else:
			M0 = self.M0
			for a in self.model.agents['agent']:
				a.goods[self.model.moneyGood] += a.goods[self.model.moneyGood]/M0 * amount
		
			for s in self.model.agents['store']:
				s.goods[self.model.moneyGood] += s.goods[self.model.moneyGood]/M0 * amount
				
	@property
	def M0(self):
		total = 0
		for lst in self.model.agents.values():
			for a in lst:
				if hasattr(a, 'reserves'): total += a.reserves #Do something about this
				else: total += a.goods[self.model.moneyGood]
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
		return mean(array(list(self.model.agents['store'][0].price.values())))
		# for s in self.model.agents['store']:
		# 	volume = sum(list(s.lastDemand.values()))
		# 	numer += mean(array(list(s.price.values()))) * volume
		# 	denom += volume
		#
		# if denom==0: return 1
		# else: return numer/denom