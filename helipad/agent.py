# ==========
# Basic extensible agent class
# Do not run this file; import model.py and run from your file.
# ==========

from random import choice
from numpy import *

#Basic agent functions. This class should not be instantiated directly; instead it should be
#subclassed by a class corresponding to a primitive and registered with Helipad.addPrimitive().
#See below, the Agent() class for a minimal example.
class baseAgent():
	def __init__(self, breed, id, model):
		self.breed = breed
		self.id = int(id)
		self.model = model
		self.age = 0
		self.dead = False
		self.goods = {}
		self.edges = {}
		self.utils = 0
		for good, params in model.goods.items():
			if params.endowment is None: self.goods[good] = 0
			elif callable(params.endowment): self.goods[good] = params.endowment(self.breed if hasattr(self, 'breed') else None)
			else: self.goods[good] = params.endowment
		
		self.currentDemand = {g:0 for g in model.goods.keys()}
		self.currentShortage = {g:0 for g in model.goods.keys()}
					
		self.model.doHooks(['baseAgentInit', self.primitive+'Init'], [self, self.model])
	
	def step(self, stage):
		self.model.doHooks(['baseAgentStep', self.primitive+'Step'], [self, self.model, stage])
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
		
		#Budget constraint and hooks
		if amount > self.balance: amount = self.balance
		if -amount > recipient.balance: amount = -recipient.balance
		amount_ = self.model.doHooks('pay', [self, recipient, amount, self.model])
		if amount_ is not None: amount = amount_
				
		if amount != 0:
			recipient.goods[self.model.moneyGood] += amount
			self.goods[self.model.moneyGood] -= amount
		return amount
	
	def reproduce(self, inherit=[], mutate={}, partners=[]):
		maxid = 0
		for a in self.model.agents['agent']:
			if a.id > maxid:
				maxid = a.id
		newagent = type(self)(self.breed, maxid+1, self.model)
		
		#Values in the inherit list can either be a variable name (in which case the new agent inherits
		#the mean of all of the values for the parents), or a tuple, the first element of which is a
		#variable name, and the second is a string representing how to merge them. Possible values are
		#'mean' (default for numeric values), 'first' (default for non-numeric values), 'last', 'gmean',
		#'random', and 'sum'. The second value can also take a function, which receives a list of
		#values from the parents and returns a value for the child.
		parents = [self] + partners
		for a in inherit:
			stat = None
			if isinstance(a, tuple): a, stat = a
			v = [getattr(p,a) for p in parents if hasattr(p,a)] #List of values, filtering those without
			if len(v)==0: continue
			
			#Default statistic if unspecified. 'mean' for numbers, and 'first' for non-numbers.
			if stat is None:
				stat = 'mean' if isinstance(v[0], (int, float, complex)) and not isinstance(v[0], bool) else 'first'
			
			if stat=='mean': n = mean(v)
			elif stat=='sum': n = sum(v)
			elif stat=='gmean': n = exp(log(v).sum()/len(v))
			elif stat=='first': n = v[0]
			elif stat=='last': n = v[len(v)-1]
			elif stat=='rand' or stat=='random': n = choice(v)
			elif stat=='max': n = max(v)
			elif stat=='min': n = min(v)
			elif callable(stat): n = stat(v)
			else: raise ValueError("Invalid statistic in reproduction function.")
			
			setattr(newagent, a, n)
		
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
		for p in parents:
			p.newEdge(newagent,'lineage', True) #Keep track of parent-child relationships
		self.model.agents[self.primitive].append(newagent)
		self.model.param('agents_'+self.primitive, self.model.param('agents_'+self.primitive)+1)
		
		self.model.doHooks(['baseAgentReproduce', self.primitive+'Reproduce'], [parents, newagent, self.model])
		return newagent
	
	def die(self):
		self.model.agents[self.primitive].remove(self)
		self.model.param('agents_'+self.primitive, self.model.param('agents_'+self.primitive)-1)
		for edge in self.alledges: edge.cut()
		self.model.doHooks(['baseAgentDie', self.primitive+'Die'], [self])
		self.dead = True
	
	def newEdge(self, partner, kind='edge', direction=None, weight=1):
		return Edge(self, partner, kind, direction, weight)
	
	def outbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError('Object must be specified either \'agent\' or \'edge\'.')
		if kind is None: edges = self.alledges
		else:
			if not kind in self.edges: return []
			edges = self.edges[kind]
		ob = [edge for edge in edges if edge.startpoint == self or (undirected and not edge.directed)]
		return ob if obj=='edge' else [e.partner(self) for e in ob]
	
	def inbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError('Object must be specified either \'agent\' or \'edge\'.')
		if kind is None: edges = self.alledges
		else:
			if not kind in self.edges: return []
			edges = self.edges[kind]
		ib = [edge for edge in edges if edge.endpoint == self or (undirected and not edge.directed)]
		return ib if obj=='edge' else [e.partner(self) for e in ib]
	
	def edgesWith(self, partner, kind='edge'):
		if kind is not None:
			if not kind in self.edges: return []
			edges = self.edges[kind]
		else: edges = self.alledges
		return [edge for edge in edges if self in edge.vertices and partner in edge.vertices]
	
	@property
	def alledges(self):
		edges = []
		for e in self.edges.values(): edges += e
		return edges
	
	@property
	def parent(self):
		p = self.inbound('lineage')
		if len(p)==0: return None
		elif len(p)==1: return p[0]
		else: return p
	
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

#The default agent class corresponding to the 'agent' primitive.	
class Agent(baseAgent):
	pass

#Direction can take an Agent object (corresponding to the endpoint),
#an int (0 for undirected, >0 for agent1 to agent2, and <0 for agent2 to agent1),
#or a boolean (False for undirected, True for agent1 to agent2)
class Edge():
	def __init__(self, agent1, agent2, kind='edge', direction=None, weight=1):
		self.active = True
		self.kind = kind
		self.vertices = (agent1, agent2)
		self.weight = weight
		self.directed = False
		if direction is not None:
			self.directed = True
			if isinstance(direction, int):
				if direction==0: self.directed = False
				elif direction>0: self.startpoint, self.endpoint = (agent1, agent2)
				elif direction<0: self.startpoint, self.endpoint = (agent2, agent1)
			elif isinstance(direction, bool):
				self.directed = direction
				if direction: self.startpoint, self.endpoint = (agent1, agent2)
			elif isinstance(direction, baseAgent):
				if direction not in self.vertices: raise ValueError('Direction must select one of the agents as an endpoint.')
				self.endpoint = direction
				self.startpoint = agent1 if direction==agent2 else agent2
			else: raise ValueError('Direction must be either int, bool, or agent.')
		if not self.directed:
			self.endpoint, self.startpoint, self.directed = (None, None, False)
		
		#Add object to each agent, and to the model
		for agent in self.vertices:
			if not kind in agent.edges: agent.edges[kind] = []
			agent.edges[kind].append(self)
		if not kind in agent1.model.allEdges: agent1.model.allEdges[kind] = []
		agent1.model.allEdges[kind].append(self)
		
		agent1.model.doHooks('edgeInit', [self, kind, agent1, agent2])
	
	def cut(self):
		for agent in self.vertices: agent.edges[self.kind].remove(self) #Remove from agents
		self.vertices[0].model.allEdges[self.kind].remove(self)			#Remove from model
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