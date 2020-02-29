# ==========
# Basic extensible agent class
# Do not run this file; import model.py and run from your file.
# ==========

from random import choice
from numpy import *

#Everybody who uses money, a base class to build upon
class baseAgent():
	def __init__(self, id, model):
		self.id = int(id)
		self.model = model
		self.age = 0
		self.dead = False
		self.goods = {}
		self.edges = {}
		for good, params in model.goods.items():
			if params.endowment is None: self.goods[good] = 0
			elif callable(params.endowment): self.goods[good] = params.endowment(self.breed if hasattr(self, 'breed') else None)
			else: self.goods[good] = params.endowment
		
		self.currentDemand = {g:0 for g in model.goods.keys()}
		self.currentShortage = {g:0 for g in model.goods.keys()}
					
		self.model.doHooks('baseAgentInit', [self, self.model])
	
	def step(self, stage):
		self.model.doHooks('baseAgentStep', [self, self.model, stage])
		if stage == self.model.stages: self.age += 1
	
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
	
	def reproduce(self, inherit=[], mutate={}):
		maxid = 0
		for a in self.model.agents['agent']:
			if a.id > maxid:
				maxid = a.id
		newagent = Agent(self.breed, maxid+1, self.model)
		
		#Copy inherited variables
		for a in inherit + list(mutate.keys()):
			if hasattr(self, a):
				setattr(newagent, a, getattr(self, a))
		
		#Mutate variables
		#Values in the mutate dict can be either a function (which takes a value and returns a value),
		#  a number (a std dev by which to mutate the value), or a tuple, the first element of which
		#  is a std dev and the second of which is either 'log' or 'linear'
		for k,v in mutate.items():
			if callable(v): newval = v(getattr(newagent, k))
			else:
				if isinstance(v, tuple): v, scale = v
				else: scale = 'linear'
					
				if scale=='log': newval = random.lognormal(log(getattr(newagent, k)), v)
				else: newval = random.normal(getattr(newagent, k), v)
			setattr(newagent, k, newval)
		
		newagent.id = maxid+1
		self.newEdge('lineage', newagent, newagent) #Keep track of parent-child relationships
		self.model.agents[self.primitive].append(newagent)
		self.model.param('agents_'+self.primitive, self.model.param('agents_'+self.primitive)+1)
		
		self.model.doHooks('agentReproduce', [self, newagent, self.model])
		return newagent
	
	def die(self):
		self.model.agents[self.primitive].remove(self)
		self.model.param('agents_'+self.primitive, self.model.param('agents_'+self.primitive)-1)
		self.model.doHooks('baseAgentDie', [self])
		self.dead = True
	
	def newEdge(self, kind, partner, direction=None, weight=1):
		return Edge(kind, self, partner, direction, weight)
	
	def outbound(self, kind=None):
		if kind is None: edges = self.alledges
		else:
			if not kind in self.edges: return []
			edges = self.edges[kind]
		ob = []
		for edge in edges:
			if edge.startpoint == self: ob.append(edge)
		return ob
	
	def inbound(self, kind=None):
		if kind is None: edges = self.alledges
		else:
			if not kind in self.edges: return []
			edges = self.edges[kind]
		ib = []
		for edge in edges:
			if edge.endpoint == self: ib.append(edge)
		return ib
	
	@property
	def alledges(self):
		edges = []
		for e in self.edges.values(): edges += e
		return edges
	
	@property
	def parent(self):
		p = self.inbound('lineage')
		return p[0].partner(self) if len(p) > 0 else None
	
	@property
	def children(self):
		return [edge.partner(self) for edge in self.outbound('lineage')]
	
	@property
	def balance(self):
		if self.model.moneyGood is None: raise RuntimeError('Balance checking requires a monetary good to be specified')
		bal = self.goods[self.model.moneyGood]
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_
		
		return bal
		
class Agent(baseAgent):
	def __init__(self, breed, id, model):
		self.breed = breed
		super().__init__(id, model)
		
		self.utils = 0
		self.model.doHooks('agentInit', [self, model])
	
	def step(self, stage):
		super().step(stage)
		self.model.doHooks('agentStep', [self, self.model, stage])
	
	def die(self):
		self.model.doHooks('agentDie', [self])
		super().die()

class Edge():
	def __init__(self, kind, agent1, agent2, direction=None, weight=1):
		self.active = True
		self.kind = kind
		self.vertices = (agent1, agent2)
		self.weight = weight
		if direction is not None:
			if direction not in self.vertices: raise ValueError('Direction must select one of the agents as an endpoint.')
			self.endpoint = direction
			self.startpoint = agent1 if direction==agent2 else agent2
			self.directed = True
		else:
			self.endpoint, self.startpoint, self.directed = (None, None, False)
		print(self.vertices)
		for agent in self.vertices:
			if not kind in agent.edges: agent.edges[kind] = []
			agent.edges[kind].append(self)
		agent1.model.doHooks('edgeInit', [self, kind, agent1, agent2])
	
	def cut(self):
		for agent in self.vertices: agent.edges[self.kind].remove(self)
		self.active = False
		self.vertices[0].model.doHooks('edgeCut', [self])
	
	def partner(self, agent):
		if agent==self.vertices[0]: return self.vertices[1]
		elif agent==self.vertices[1]: return self.vertices[0]
		else: raise ValueError('Agent',agent.id,'is not connected to this edge.')
	
	def reassign(self, oldagent, newagent):
		self.vertices = (self.partner(oldagent), newagent)
		oldagent.edges[self.kind].remove(self)
		newagent.edges[self.kind].append(self)
		newagent.model.doHooks('edgeReassign', [self, oldagent, newagent])