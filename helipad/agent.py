# ==========
# Basic extensible agent class
# Do not run this file; import model.py and run from your file.
# ==========

import warnings
from random import choice, randint
import numpy as np

#Basic agent functions. This class should not be instantiated directly; instead it should be
#subclassed by a class corresponding to a primitive and registered with Helipad.addPrimitive().
#See below, the Agent() class for a minimal example.
class baseAgent:
	fixed = False
	overdraft = 'continue-silent'

	#==================
	# BASIC METHODS
	#==================

	def __init__(self, breed, aId, model):
		self.breed = breed
		self.id = int(aId)
		self.model = model
		self.age = 0
		self.dead = False
		self.stocks = Stocks(breed, model.goods)
		self.edges = {}
		self.utils = 0
		self.position = None #Overridden in spatial init
		self.currentDemand = {g:0 for g in model.goods.keys()}

		#For multi-level models
		#Has to be a static property since we're checking as the object initializes
		if hasattr(super(), 'runInit'): super().__init__()

		self.model.doHooks(['baseAgentInit', self.primitive+'Init'], [self, self.model])

	def step(self, stage):
		self.model.doHooks(['baseAgentStep', self.primitive+'Step'], [self, self.model, stage])
		if hasattr(super(), 'runInit'): super().step(stage) #For multi-level models
		if stage == self.model.stages: self.age += 1

	#==================
	# ECONOMIC METHODS
	#==================

	#Give amt1 of good 1, get amt2 of good 2
	#Negative values of amt1 and amt2 allowed, which reverses the direction
	def trade(self, partner, good1, amt1, good2, amt2):
		go = True
		self.model.doHooks('preTrade', [self, partner, good1, amt1, good2, amt2])

		#Budget constraints. Hold price constant if hit
		message = None
		prim1, prim2 = self.primitive.title(), partner.primitive.title()
		if amt2 != 0: price = amt1 / amt2
		if self.overdraft != 'allow':
			if amt1 > self.stocks[good1]:
				message = _('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim1, self.id, good1, prim2, partner.id)
				if 'continue' in self.overdraft:
					message += _(' Continuing with available {0} of {1}…').format(good1, self.stocks[good1])
					amt1 = self.stocks[good1]
					if amt2 != 0: amt2 = amt1 / price
			elif -amt1 > partner.stocks[good1]:
				message = _('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim2, partner.id, good1, prim1, self.id)
				if 'continue' in self.overdraft:
					message += _(' Continuing with available {0} of {1}…').format(good1, partner.stocks[good1])
					amt1 = -partner.stocks[good1]
					if amt2 != 0: amt2 = amt1 / price
			if amt2 > partner.stocks[good2]:
				message = _('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim2, partner.id, good2, prim1, self.id)
				if 'continue' in self.overdraft:
					message += _(' Continuing with available {0} of {1}…').format(good2, partner.stocks[good2])
					amt2 = partner.stocks[good2]
					amt1 = price * amt2
			elif -amt2 > self.stocks[good2]:
				message = _('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim1, self.id, good2, prim2, partner.id)
				if 'continue' in self.overdraft:
					message += _(' Continuing with available {0} of {1}…').format(good2, self.stocks[good2])
					amt2 = -self.stocks[good2]
					amt1 = price * amt2

			if message is not None:
				if self.overdraft == 'stop': raise ValueError(message)
				if 'fail' in self.overdraft:
					go = False
					message += _(' Cancelling trade…')
				elif 'warn' in self.overdraft: warnings.warn(message, None, 2)

		if go:
			self.stocks[good1] -= amt1
			partner.stocks[good1] += amt1
			self.stocks[good2] += amt2
			partner.stocks[good2] -= amt2

			#Record demand
			if amt1 > 0: partner.currentDemand[good1] += amt1
			else: self.currentDemand[good1] -= amt1
			if amt2 > 0: self.currentDemand[good2] += amt2
			else: partner.currentDemand[good2] -= amt2

		self.model.doHooks('postTrade', [self, partner, good1, amt1, good2, amt2])

	#Price is per-unit
	#Returns the quantity actually sold, Which is the same as quantity input unless there's a shortage
	def buy(self, partner, good, q, p):
		if self.model.goods.money is None: raise RuntimeError(_('{} requires a monetary good to be specified.').format('Agent.buy()'))
		qp = self.model.doHooks('buy', [self, partner, good, q, p])
		if qp is not None: q, p = qp

		before = self.stocks[good]
		self.trade(partner, self.model.goods.money, p*q, good, q)
		return self.stocks[good] - before

	#Unilateral
	def pay(self, recipient, amount):
		if self.model.goods.money is None: raise RuntimeError(_('{} requires a monetary good to be specified.').format('Agent.pay()'))
		go = True

		#Do hooks before budget constraints
		amount_ = self.model.doHooks('pay', [self, recipient, amount, self.model])
		if amount_ is not None: amount = amount_

		#Budget constraints
		prim1, prim2 = self.primitive.title(), recipient.primitive.title()
		message = None
		if self.overdraft != 'allow':
			if amount > self.balance:
				message = _('{0} {1} does not have sufficient funds to pay {2} {3}.').format(prim1, self.id, prim2, recipient.id)
				if self.overdraft == 'stop': raise ValueError(message)
				if 'continue' in self.overdraft:
					amount = self.balance
					message += _(' Continuing with available balance of {}…').format(self.balance)
			elif -amount > recipient.balance:
				message = _('{0} {1} does not have sufficient funds to pay {2} {3}.').format(prim2, recipient.id, prim1, self.id)
				if 'continue' in self.overdraft:
					amount = -recipient.balance
					message += _(' Continuing with available balance of {}…').format(recipient.balance)

			if message is not None:
				if self.overdraft == 'stop': raise ValueError(message)
				if 'fail' in self.overdraft:
					go = False
					message += _(' Cancelling trade…')
				if 'warn' in self.overdraft:
					warnings.warn(message, None, 2)

		if go and amount:
			recipient.stocks[self.model.goods.money] += amount
			self.stocks[self.model.goods.money] -= amount
			return amount
		else: return 0

	@property
	def balance(self):
		if self.model.goods.money is None: raise RuntimeError(_('Balance checking requires a monetary good to be specified.'))
		bal = self.stocks[self.model.goods.money]
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_

		return bal

	#==================
	# GENETIC METHODS
	#==================

	def reproduce(self, inherit=[], mutate={}, partners=[]):
		if self.fixed: raise NotImplementedError(_('Fixed primitives cannot reproduce.'))

		maxid = 0
		for a in self.model.allagents.values():
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

			if stat=='mean': n = np.mean(v)
			elif stat=='sum': n = sum(v)
			elif stat=='gmean': n = np.exp(np.log(v).sum()/len(v))
			elif stat=='first': n = v[0]
			elif stat=='last': n = v[len(v)-1]
			elif stat in ('rand', 'random'): n = choice(v)
			elif stat=='max': n = max(v)
			elif stat=='min': n = min(v)
			elif callable(stat): n = stat(v)
			else: raise ValueError(_('Invalid statistic {}.').format(stat))

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

				if scale=='log': newval = np.random.lognormal(np.log(getattr(newagent, k)), v)
				else: newval = np.random.normal(getattr(newagent, k), v)
			setattr(newagent, k, newval)

		newagent.id = maxid+1
		for p in parents:
			p.newEdge(newagent,'lineage', True) #Keep track of parent-child relationships
		self.model.agents[self.primitive].append(newagent)

		self.model.doHooks(['baseAgentReproduce', self.primitive+'Reproduce'], [parents, newagent, self.model])
		return newagent

	def die(self, updateGUI=True):
		if self.fixed: raise NotImplementedError(_('Fixed primitives cannot die.'))
		self.model.agents[self.primitive].remove(self)
		for edge in self.alledges: edge.cut()
		self.dead = True
		self.model.doHooks(['baseAgentDie', self.primitive+'Die'], [self])

	@property
	def parent(self):
		p = self.inbound('lineage', obj='agent')
		if len(p)==0: return None
		elif len(p)==1: return p[0]
		else: return p

	@property
	def children(self):
		return [edge.partner(self) for edge in self.outbound('lineage')]

	#==================
	# NETWORK METHODS
	#==================

	def newEdge(self, partner, kind='edge', direction=None, weight=1):
		return Edge(self, partner, kind, direction, weight)

	def outbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError(_('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.alledges
		else:
			if kind not in self.edges: return []
			edges = self.edges[kind]
		ob = [edge for edge in edges if edge.startpoint == self or (undirected and not edge.directed)]
		return ob if obj=='edge' else [e.partner(self) for e in ob]

	def inbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError(_('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.alledges
		else:
			if kind not in self.edges: return []
			edges = self.edges[kind]
		ib = [edge for edge in edges if edge.endpoint == self or (undirected and not edge.directed)]
		return ib if obj=='edge' else [e.partner(self) for e in ib]

	def edgesWith(self, partner, kind='edge'):
		if kind is not None:
			if kind not in self.edges: return []
			edges = self.edges[kind]
		else: edges = self.alledges
		return [edge for edge in edges if self in edge.vertices and partner in edge.vertices]

	@property
	def alledges(self):
		edges = []
		for e in self.edges.values(): edges += e
		return edges

	#==================
	# OTHER METHODS
	#==================

	#In a multi-level model, allow the agent to move to a different deme/firm/etc
	def transfer(self, dest):
		origin = self.model
		dest.agents[self.primitive].append(self)
		self.model = dest
		origin.agents[self.primitive].remove(self)
		self.model.doHooks(['baseAgentMove', self.primitive+'Move'], [self, origin, dest])

#The default agent class corresponding to the 'agent' primitive.
class Agent(baseAgent):
	pass

#For spatial models
class Patch(baseAgent):
	fixed = True

	@property
	def neighbors(self):
		return self.outbound('space', True, obj='agent')

	@property
	def up(self):
		if self.y==0 and not self.model.param('wrap'): return None
		return self.model.patches[self.x, self.y-1 if self.y > 0 else self.model.param('y')-1]

	@property
	def right(self):
		if self.x>=self.model.param('x')-1 and not self.model.param('wrap'): return None
		return self.model.patches[self.x+1 if self.x < self.model.param('x')-1 else 0, self.y]

	@property
	def down(self):
		if self.y>=self.model.param('y')-1 and not self.model.param('wrap'): return None
		return self.model.patches[self.x, self.y+1 if self.y < self.model.param('y')-1 else 0]

	@property
	def left(self):
		if self.x==0 and not self.model.param('wrap'): return None
		return self.model.patches[self.x-1 if self.x > 0 else self.model.param('x')-1, self.y]

	@property
	def agentsOn(self):
		for prim, lst in self.model.agents.items():
			if prim=='patch': continue
			yield from [a for a in lst if self.x-0.5<=a.x<self.x+0.5 and self.y-0.5<=a.y<self.y+0.5]

#Direction can take an Agent object (corresponding to the endpoint),
#an int (0 for undirected, >0 for agent1 to agent2, and <0 for agent2 to agent1),
#or a boolean (False for undirected, True for agent1 to agent2)
class Edge:
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
				if direction not in self.vertices: raise ValueError(_('Direction must select one of the agents as an endpoint.'))
				self.endpoint = direction
				self.startpoint = agent1 if direction==agent2 else agent2
			else: raise ValueError(_('Direction must be either int, bool, or agent.'))
		if not self.directed:
			self.endpoint, self.startpoint, self.directed = (None, None, False)

		#Add object to each agent, and to the model
		for agent in self.vertices:
			if not kind in agent.edges: agent.edges[kind] = []
			if not self in agent.edges[kind]: agent.edges[kind].append(self) #Don't add self-links twice

		agent1.model.doHooks('edgeInit', [self, kind, agent1, agent2])

	def cut(self):
		for agent in self.vertices:
			if self in agent.edges[self.kind]: agent.edges[self.kind].remove(self) #Remove from agents
		self.active = False
		self.vertices[0].model.doHooks('edgeCut', [self])

	def partner(self, agent):
		if agent==self.vertices[0]: return self.vertices[1]
		elif agent==self.vertices[1]: return self.vertices[0]
		else: raise ValueError(_('Agent {} is not connected to this edge.').format(agent.id))

	def reassign(self, oldagent, newagent):
		self.vertices = (self.partner(oldagent), newagent)
		oldagent.edges[self.kind].remove(self)
		newagent.edges[self.kind].append(self)
		newagent.model.doHooks('edgeReassign', [self, oldagent, newagent])

class Stocks:
	def __init__(self, breed, goodslist):
		self.goods = {g:{} for g in goodslist}
		for good, ginfo in goodslist.items():
			for p, fn in ginfo.props.items():
				endow = fn(breed) if callable(fn) else fn
				if endow is None: self.goods[good][p] = 0
				elif isinstance(endow, (tuple, list)): self.goods[good][p] = randint(*endow)
				else: self.goods[good][p] = endow

	def __getitem__(self, key):
		if isinstance(key, str): return self.goods[key]['quantity']
		elif isinstance(key, tuple):
			if isinstance(key[1], str): return self.goods[key[0]][key[1]]
			elif key[1] is True: return self.goods[key[0]]
			elif key[1] is False: return self.goods[key]['quantity']
		raise KeyError

	def __setitem__(self, key, val):
		if isinstance(key, str): self.goods[key]['quantity'] = val
		elif isinstance(key, tuple) and isinstance(key[1], str): self.goods[key[0]][key[1]] = val
		else: raise KeyError

	def __iter__(self): return iter({k: g['quantity'] for k,g in self.goods.items()})
	def __next__(self): return next({k: g['quantity'] for k,g in self.goods.items()})
	def __len__(self): return len(self.goods)
	def keys(self): return self.goods.keys()
	def values(self): return [g['quantity'] for g in self.goods.values()]
	def items(self): return [(k, g['quantity']) for k,g in self.goods.items()]