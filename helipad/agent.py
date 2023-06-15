"""
The `Agent` class and the `Agents` container. This module can be imported to extend `baseAgent` to create new primitives.
"""

import warnings
from random import choice, randint, shuffle
from math import degrees, radians, pi
import numpy as np
import pandas
from helipad.helpers import ï, funcStore, Color, Item, isNotebook

#Basic agent functions. This class should not be instantiated directly; instead it should be
#subclassed by a class corresponding to a primitive and registered with Helipad.addPrimitive().
#See below, the Agent() class for a minimal example.
class baseAgent:
	"""A basic agent class that can be subclassed to create new primitives (see https://helipad.dev/functions/agents/addprimitive/). https://helipad.dev/functions/baseagent/"""
	angleUnit: str = 'deg'
	fixed: bool = False
	overdraft: str = 'continue-silent'

	#==================
	# BASIC METHODS
	#==================

	def __init__(self, breed: str, aId: int, model):
		self.breed = breed
		self.id = int(aId)
		self.model = model
		self.age = 0
		self.dead = False
		self.stocks = Stocks(breed, model.goods)
		self.edges = Edges(self)
		self.utils = 0
		if not hasattr(self, 'position'): self.position = None #Overridden in spatial init
		self.currentDemand = {g:0 for g in model.goods.keys()}
		self.rads = 0

		#For multi-level models
		#Has to be a static property since we're checking as the object initializes
		if hasattr(super(), 'runInit'): super().__init__()

		self.model.doHooks(['baseAgentInit', self.primitive+'Init'], [self, self.model])

	def __repr__(self): return f'<{self.__class__.__name__} {self.id}>'

	def step(self, stage: int):
		"""Runs for each agent in each period and increments the agent's age by 1. Should not be called directly, but should be hooked using `agentStep` or `baseAgentStep`. https://helipad.dev/functions/baseagent/step/"""
		self.model.doHooks(['baseAgentStep', self.primitive+'Step'], [self, self.model, stage])
		if hasattr(super(), 'runInit'): super().step(stage) #For multi-level models
		if stage == self.model.stages: self.age += 1

	#==================
	# ECONOMIC METHODS
	#==================

	def trade(self, partner, good1: str, amt1, good2: str, amt2):
		"""Exchange `amt1` of `good1` with `partner` for `amt2` of `good2`, and record the demand for each. Requires at least two goods to have been registered, but does not require a monetary good. Negative amounts are allowed, which reverses the direction. https://helipad.dev/functions/baseagent/trade/"""
		go = True
		self.model.doHooks('preTrade', [self, partner, good1, amt1, good2, amt2])

		#Budget constraints. Hold price constant if hit
		message = None
		prim1, prim2 = self.primitive.title(), partner.primitive.title()
		if amt2 != 0: price = amt1 / amt2
		if self.overdraft != 'allow':
			if amt1 > self.stocks[good1]:
				message = ï('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim1, self.id, good1, prim2, partner.id)
				if 'continue' in self.overdraft:
					message += ï(' Continuing with available {0} of {1}…').format(good1, self.stocks[good1])
					amt1 = self.stocks[good1]
					if amt2 != 0: amt2 = amt1 / price
			elif -amt1 > partner.stocks[good1]:
				message = ï('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim2, partner.id, good1, prim1, self.id)
				if 'continue' in self.overdraft:
					message += ï(' Continuing with available {0} of {1}…').format(good1, partner.stocks[good1])
					amt1 = -partner.stocks[good1]
					if amt2 != 0: amt2 = amt1 / price
			if amt2 > partner.stocks[good2]:
				message = ï('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim2, partner.id, good2, prim1, self.id)
				if 'continue' in self.overdraft:
					message += ï(' Continuing with available {0} of {1}…').format(good2, partner.stocks[good2])
					amt2 = partner.stocks[good2]
					amt1 = price * amt2
			elif -amt2 > self.stocks[good2]:
				message = ï('{0} {1} does not have sufficient {2} to give {3} {4}.').format(prim1, self.id, good2, prim2, partner.id)
				if 'continue' in self.overdraft:
					message += ï(' Continuing with available {0} of {1}…').format(good2, self.stocks[good2])
					amt2 = -self.stocks[good2]
					amt1 = price * amt2

			if message is not None:
				if self.overdraft == 'stop': raise ValueError(message)
				if 'fail' in self.overdraft:
					go = False
					message += ï(' Cancelling trade…')
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

	def buy(self, partner, good: str, q, p):
		"""Purchase `q` of `good` from `partner` at a per-unit price of `p` in terms of the monetary good. Returns the quantity actually sold, which is the same as `q` unless there's a shortage. https://helipad.dev/functions/baseagent/buy/"""
		if self.model.goods.money is None: raise RuntimeError(ï('{} requires a monetary good to be specified.').format('Agent.buy()'))
		qp = self.model.doHooks('buy', [self, partner, good, q, p])
		if qp is not None: q, p = qp

		before = self.stocks[good]
		self.trade(partner, self.model.goods.money, p*q, good, q)
		return self.stocks[good] - before

	def pay(self, recipient, amount):
		"""Unilaterally transfer `amount` of the monetary good to `recipient`, or from `recipient` to the agent if `amount<0`. Returns the amount actually paid, which will be equal to `amount` unless the agent's budget constraint is hit. https://helipad.dev/functions/baseagent/pay/"""
		if self.model.goods.money is None: raise RuntimeError(ï('{} requires a monetary good to be specified.').format('Agent.pay()'))
		go = True

		#Do hooks before budget constraints
		amount_ = self.model.doHooks('pay', [self, recipient, amount, self.model])
		if amount_ is not None: amount = amount_

		#Budget constraints
		prim1, prim2 = self.primitive.title(), recipient.primitive.title()
		message = None
		if self.overdraft != 'allow':
			if amount > self.balance:
				message = ï('{0} {1} does not have sufficient funds to pay {2} {3}.').format(prim1, self.id, prim2, recipient.id)
				if self.overdraft == 'stop': raise ValueError(message)
				if 'continue' in self.overdraft:
					amount = self.balance
					message += ï(' Continuing with available balance of {}…').format(self.balance)
			elif -amount > recipient.balance:
				message = ï('{0} {1} does not have sufficient funds to pay {2} {3}.').format(prim2, recipient.id, prim1, self.id)
				if 'continue' in self.overdraft:
					amount = -recipient.balance
					message += ï(' Continuing with available balance of {}…').format(recipient.balance)

			if message is not None:
				if self.overdraft == 'stop': raise ValueError(message)
				if 'fail' in self.overdraft:
					go = False
					message += ï(' Cancelling trade…')
				if 'warn' in self.overdraft:
					warnings.warn(message, None, 2)

		if go and amount:
			recipient.stocks[self.model.goods.money] += amount
			self.stocks[self.model.goods.money] -= amount
			return amount
		else: return 0

	@property
	def balance(self):
		"""If a monetary good is registered, the agent's holdings of the monetary good. Equivalent to `agent.stocks[model.goods.money]`. https://helipad.dev/functions/baseagent/#balance"""
		if self.model.goods.money is None: raise RuntimeError(ï('Balance checking requires a monetary good to be specified.'))
		bal = self.stocks[self.model.goods.money]
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_

		return bal

	#==================
	# GENETIC METHODS
	#==================

	def reproduce(self, inherit: list=[], mutate: dict={}, partners: list=[]):
		"""Spawn a new agent, inheriting specified properties from the parent agent(s).
		
		Values in `inherit` can either be a property name (in which case the new agent inherits the mean of the parents' values), or a tuple, the first element of which is a property name, and the second is a string representing how to merge them. Possible values are `'mean'` (default for numeric values), `'first'` (default for non-numeric values), `'last'`, `'gmean'`, `'random'`, and `'sum'`. The second value can also take a function, which receives a list of values from the parents and returns a value for the child.
		
		Keys of `mutate` correspond to property names, which will mutate either a property value retrieved from `inherit` or the initial value otherwise. Dict values can be either (1) a function (which takes a value and returns a value), (2) a std dev by which to mutate the value in a normal distribution with mean of the initial value, or (3) a tuple, the first item of which is a stdev and the second is either `'log'` or `'linear'` (i.e. to sample from a lognormal distribution).

		https://helipad.dev/functions/baseagent/reproduce/"""
		if self.fixed: raise NotImplementedError(ï('Fixed primitives cannot reproduce.'))

		maxid = 0
		for a in self.model.agents.all:
			if a.id > maxid:
				maxid = a.id
		newagent = type(self)(self.breed, maxid+1, self.model)

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
			else: raise ValueError(ï('Invalid statistic {}.').format(stat))

			setattr(newagent, a, n)

		#Mutate variables
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
			p.edges.add(newagent,'lineage', True) #Keep track of parent-child relationships
		self.model.agents[self.primitive].append(newagent)

		self.model.doHooks(['baseAgentReproduce', self.primitive+'Reproduce'], [parents, newagent, self.model])
		return newagent

	def die(self, updateGUI: bool=True):
		"""Remove the agent from the model's list of active agents and cut the agent's edges. https://helipad.dev/functions/baseagent/die/"""
		if self.fixed: raise NotImplementedError(ï('Fixed primitives cannot die.'))
		self.model.agents[self.primitive].remove(self)
		for edge in self.edges.all: edge.cut()
		self.dead = True
		self.model.doHooks(['baseAgentDie', self.primitive+'Die'], [self])

	@property
	def parent(self):
		"""The agent (if haploid) or a list of agents (if polyploid) from which the current agent was spawned. See `agent.reproduce()`. https://helipad.dev/functions/baseagent/#parent"""
		p = self.inbound('lineage', obj='agent')
		if len(p)==0: return None
		elif len(p)==1: return p[0]
		else: return p

	@property
	def children(self):
		"""A list of agents spawned from the current agent. See `agent.reproduce()`. https://helipad.dev/functions/baseagent/#children"""
		return [edge.partner(self) for edge in self.outbound('lineage')]

	#==================
	# NETWORK METHODS
	# All deprecated in Helipad 1.6, remove in Helipad 1.8
	#==================

	def newEdge(self, partner, kind='edge', direction=None, weight=1):
		"""Create a network connection with `partner`. This method is deprecated; use `Agent.edges.add()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.newEdge()', 'Agent.edges.add()'), FutureWarning, 2)
		return self.edges.add(partner, kind, direction, weight)

	def outbound(self, kind='edge', undirected=False, obj='edge'):
		"""Return a list of outbound edges. This method is deprecated; use `Agent.edges.outbound()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.outbound()', 'Agent.edges.outbound()'), FutureWarning, 2)
		return self.edges.outbound(kind, undirected, obj)

	def inbound(self, kind='edge', undirected=False, obj='edge'):
		"""Return a list of inbound edges. This method is deprecated; use `Agent.edges.inbound()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.inbound()', 'Agent.edges.inbound()'), FutureWarning, 2)
		return self.edges.inbound(kind, undirected, obj)

	def edgesWith(self, partner, kind='edge'):
		"""Return a list of connections with `partner`. This method is deprecated; use `Agent.edges.With()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.edgesWith()', 'Agent.edges.With()'), FutureWarning, 2)
		return self.edges.With(partner, kind)

	@property
	def alledges(self):
		"""A list of all the agent's network connections, organized by network kind. This method is deprecated; use `Agent.edges` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.allEdges', 'Agent.edges.all'), FutureWarning, 2)
		return self.edges.all

	#==================
	# OTHER METHODS
	#==================

	#Agent.orientation reports and sets degrees or radians, depending on Agent.angleUnit.
	#Agent.rads always reports radians and is not documented.
	@property
	def orientation(self):
		"""The orientation of the agent on the spatial grid. This property returns and can be set in either degrees or radians, depending on the value of `baseAgent.angleUnit`. https://helipad.dev/functions/baseagent/#orientation"""
		if self.primitive == 'patch': return None
		return degrees(self.rads) if 'deg' in self.angleUnit else self.rads

	@orientation.setter
	def orientation(self, val):
		if self.primitive == 'patch': raise RuntimeError(ï('Patches cannot rotate.'))
		if 'deg' in self.angleUnit: val = radians(val)
		while val >= 2*pi: val -= 2*pi
		while val < 0: val += 2*pi
		self.rads = val

	def rotate(self, angle):
		"""Rotate the agent's orientation clockwise by `angle`, which will be understood as either degrees or radians depending on the value of `baseAgent.angleUnit`. https://helipad.dev/functions/baseagent/rotate/"""
		self.orientation += angle

	@property
	def patch(self):
		"""The patch under the agent's current position. https://helipad.dev/functions/baseagent/#patch"""
		if self.position is not None: return self.model.patches.at(*self.position)

	def transfer(self, dest):
		"""In a multi-level model, move the agent to a different instance of `MultiLevel` or the top-level model."""
		origin = self.model
		dest.agents[self.primitive].append(self)
		self.model = dest
		origin.agents[self.primitive].remove(self)
		self.model.doHooks(['baseAgentMove', self.primitive+'Move'], [self, origin, dest])

#The default agent class corresponding to the 'agent' primitive.
class Agent(baseAgent):
	"""The default agent class. https://helipad.dev/functions/agent/"""

#For spatial models
class Patch(baseAgent):
	"""A spatially and numerically fixed agent primitive that forms the layout on which other agents move in a spatial model. https://helipad.dev/functions/patch/"""
	fixed: bool = True

	#Don't remove from the list; just mark as dead
	def die(self):
		"""Remove the patch from the board, and if `model.spatial()` had been initialized with `offmap=False`, prevent agents from moving to coordinates previously covered by the patch. Patches can be revived with `Patches2D.revive()`. https://helipad.dev/functions/patch/die/"""
		self.dead = True
		if not self.model.patches.offmap:
			for a in self.agentsOn: a.die()
		self.model.doHooks(['baseAgentDie', 'PatchDie'], [self])

	@property
	def neighbors(self) -> list:
		"""A list of adjacent patches. Corner-adjacent patches will be included depending on the value of the `corners` parameter of `model.spatial()`. https://helipad.dev/functions/patch/#neighbors"""
		return [p for p in self.edges.outbound('space', True, obj='agent') if not p.dead]

	def __repr__(self):
		if self.model.patches.geometry == 'geo' and self.name: return f'<Patch {self.name}>'
		return f'<Patch at {self.position[0]},{self.position[1]}>'

#Direction can take an Agent object (corresponding to the endpoint),
#an int (0 for undirected, >0 for agent1 to agent2, and <0 for agent2 to agent1),
#or a boolean (False for undirected, True for agent1 to agent2)
class Edge:
	"""A connection between two agents as part of a network. https://helipad.dev/functions/edge/"""
	def __init__(self, agent1: baseAgent, agent2: baseAgent, kind: str='edge', direction=None, weight=1):
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
				if direction not in self.vertices: raise ValueError(ï('Direction must select one of the agents as an endpoint.'))
				self.endpoint = direction
				self.startpoint = agent1 if direction==agent2 else agent2
			else: raise ValueError(ï('Direction must be either int, bool, or agent.'))
		if not self.directed:
			self.endpoint, self.startpoint, self.directed = (None, None, False)

		#Add object to each agent, and to the model
		for agent in self.vertices:
			if not kind in agent.edges: agent.edges[kind] = []
			if not self in agent.edges[kind]: agent.edges[kind].append(self) #Don't add self-links twice

		agent1.model.doHooks('edgeInit', [self, kind, agent1, agent2])

	def __repr__(self):
		pair, arrow = (self.vertices, '—') if not self.directed else ((self.startpoint, self.endpoint), '→')
		return f'<{self.__class__.__name__}: {pair[0].__class__.__name__} {pair[0].id} {arrow} {pair[1].__class__.__name__} {pair[1].id}>'

	def cut(self):
		"""Break the connection between the two agents represented by the edge and remove the `Edge` object from the `edges` property of both agents. https://helipad.dev/functions/edge/cut/"""
		for agent in self.vertices:
			if self in agent.edges[self.kind]: agent.edges[self.kind].remove(self) #Remove from agents
		self.active = False
		self.vertices[0].model.doHooks('edgeCut', [self])

	def partner(self, agent: baseAgent):
		"""When passed an agent, returns the other agent. https://helipad.dev/functions/edge/partner/"""
		if agent==self.vertices[0]: return self.vertices[1]
		elif agent==self.vertices[1]: return self.vertices[0]
		else: raise ValueError(ï('Agent {} is not connected to this edge.').format(agent.id))

	def reassign(self, oldagent: baseAgent, newagent: baseAgent):
		"""Moves a vertex from `oldagent` to `newagent`. https://helipad.dev/functions/edge/reassign/"""
		self.vertices = (self.partner(oldagent), newagent)
		oldagent.edges[self.kind].remove(self)
		newagent.edges[self.kind].append(self)
		newagent.model.doHooks('edgeReassign', [self, oldagent, newagent])

class Stocks:
	"A dict-like interface for agent holdings of registered goods. https://helipad.dev/functions/baseagent/#stocks"
	def __init__(self, breed: str, goodslist: list):
		self.goods = {g:{} for g in goodslist}
		for good, ginfo in goodslist.items():
			for p, fn in ginfo.props.items():
				endow = fn(breed) if callable(fn) else fn
				if endow is None: self.goods[good][p] = 0
				elif isinstance(endow, (tuple, list)): self.goods[good][p] = randint(*endow)
				else: self.goods[good][p] = endow

	def __getitem__(self, key: str):
		if isinstance(key, str): return self.goods[key]['quantity']
		elif isinstance(key, tuple):
			if isinstance(key[1], str): return self.goods[key[0]][key[1]]
			elif key[1] is True: return self.goods[key[0]]
			elif key[1] is False: return self.goods[key]['quantity']
		raise KeyError

	def __setitem__(self, key: str, val):
		if isinstance(key, str): self.goods[key]['quantity'] = val
		elif isinstance(key, tuple) and isinstance(key[1], str): self.goods[key[0]][key[1]] = val
		else: raise KeyError

	def __repr__(self): return {k: g['quantity'] for k,g in self.goods.items()}.__repr__()
	def __iter__(self): return iter({k: g['quantity'] for k,g in self.goods.items()})
	def __next__(self): return next({k: g['quantity'] for k,g in self.goods.items()})
	def __len__(self): return len(self.goods)
	def keys(self): return self.goods.keys()
	def values(self): return [g['quantity'] for g in self.goods.values()]
	def items(self): return [(k, g['quantity']) for k,g in self.goods.items()]

#==================
# CONTAINER CLASSES
#==================

class MultiDict(dict):
	"""A base class for a dict of dicts"""
	def __len__(self):
		return sum(len(a) for a in super().values())

	@property
	def all(self) -> list:
		"""A list of all items contained."""
		agents = []
		for l in self.values(): agents += l
		return agents

class Agents(MultiDict):
	"""Interface for storing and interacting with model agents, organized by primitive. Accessible at `model.agents`. https://helipad.dev/functions/agents/"""
	def __init__(self, model):
		self.model = model
		self.order = 'linear'
		self.edges = ModelEdges(self)
		super().__init__()

	#Allow retrieval by either primitive or agent ID
	def __getitem__(self, val):
		if isinstance(val, int):
			for p in super().values():
				for a in p:
					if a.id==val: return a
		else: return super().__getitem__(val)

	def __contains__(self, val) -> bool:
		if isinstance(val, int): return self[val]
		else: return super().__contains__(val)

	def addPrimitive(self, name: str, class_, plural=None, dflt=50, low=1, high=100, step=1, hidden: bool=False, priority: int=100, order=None):
		"""Register an agent primitive. https://helipad.dev/functions/agents/addprimitive/"""
		if name=='all': raise ValueError(ï('{} is a reserved name. Please choose another.').format(name))
		if not plural: plural = name+'s'
		class_.primitive = name
		self[name] = Primitive(
			class_=class_,
			plural=plural,
			priority=priority,
			order=order,
			breeds=Breeds(self.model, name)
		)
		sort = dict(sorted(self.items(), key=lambda d: d[1].priority))
		self.clear()
		self.update(sort)

		def popget(name, model):
			prim = name.split('_')[1]
			if not model.hasModel: return None
			else: return len(model.agents[prim])
		self.model.params.add('num_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step} if not hidden else None, setter=self.initialize, getter=popget)

	def removePrimitive(self, name: str):
		"""Removes a previously added primitive. https://helipad.dev/functions/agents/removeprimitive/"""
		del self[name]
		del self.model.params['num_'+name]

	def addBreed(self, name: str, color, prim=None):
		"""Registers an agent breed. https://helipad.dev/functions/agents/addbreed/"""
		if prim is None:
			if len(super().keys()) == 1: prim = next(iter(self.keys()))
			else: raise KeyError(ï('Breed must specify which primitive it belongs to.'))
		return self[prim].breeds.add(name, color)

	#Creates an unweighted and undirected network of a certain density
	def createNetwork(self, density: float, kind: str='edge', prim=None):
		"""Create a random undirected and unweighted network of a certain `density`∈[0,1] among agents of primitive `prim`. https://helipad.dev/functions/agents/createnetwork/"""
		if density < 0 or density > 1: raise ValueError(ï('Network density must take a value between 0 and 1.'))
		from itertools import combinations
		agents = self.all if prim is None else self[prim]
		for c in combinations(agents, 2):
			if np.random.randint(0,100) < density*100:
				c[0].edges.add(c[1], kind)
		return self.network(kind, prim)

	def network(self, kind: str='edge', prim=None, excludePatches: bool=False):
		"""Export the model's graph structure to a `NetworkX` object. Agent breed, primitive, and (if a spatial model) position are stored as metadata. https://helipad.dev/functions/agents/network/"""
		import networkx as nx

		#Have to use DiGraph in order to draw any arrows
		G = nx.DiGraph(name=kind)
		agents = list(self.all) if prim is None else self[prim]
		if excludePatches: agents = [a for a in agents if a.primitive!='patch']
		G.add_nodes_from([(a.id, {'breed': a.breed, 'primitive': a.primitive, 'position': None if a.position is None else list(a.position)}) for a in agents])
		for e in self.edges[kind]:
			if prim is None or (e.vertices[0].primitive==prim and e.vertices[1].primitive==prim): G.add_edge(
				e.startpoint.id if e.directed else e.vertices[0].id,
				e.endpoint.id if e.directed else e.vertices[1].id,
				weight=e.weight, directed=e.directed
			)
		return G

	#Model param redundant, strictly speaking, but it's necessary to make the signature match the setter callback
	def initialize(self, val, prim: str, model=None, force: bool=False):
		"""Create and/or destroy agents to get a population number. This function is used as a setter function for agent population parameters, and also at the beginning of a model to create the initial agent set. https://helipad.dev/functions/agents/initialize/"""
		if not self.model.hasModel and not force: return val

		if 'num_' in prim: prim = prim.split('_')[1] #Because the parameter callback passes num_{prim}
		array = self[prim]
		diff = val - len(array)

		#Add agents
		if diff > 0:
			maxid = max(ids) if (ids := [a.id for a in self.all]) else 0 #Figure out maximum existing ID
			for aId in range(maxid+1, maxid+int(diff)+1):
				breed = self.model.doHooks([prim+'DecideBreed', 'decideBreed'], [aId, self[prim].breeds.keys(), self.model])
				if breed is None: breed = list(self[prim].breeds.keys())[aId%len(self[prim].breeds)]
				if not breed in self[prim].breeds:
					raise ValueError(ï('Breed \'{0}\' is not registered for the \'{1}\' primitive.').format(breed, prim))
				new = self[prim].class_(breed, aId, self.model)
				array.append(new)

		#Remove agents
		elif diff < 0:
			shuffle(array) #Delete agents at random

			#Remove agents, maintaining the proportion between breeds
			n = {x: 0 for x in self[prim].breeds.keys()}
			for a in self[prim]:
				if n[a.breed] < -diff:
					n[a.breed] += 1
					a.die(updateGUI=False)
				else: continue

	#Returns summary statistics on an agent variable at a single point in time
	def summary(self, var: str, prim=None, breed=None, good: bool=False):
		"""Print summary statistics (n, mean, standard deviation, variance, maximum, minimum, and sum) for an agent property. https://helipad.dev/functions/agents/summary/"""
		if prim is None:
			prim = 'agent' if 'agent' in self else next(iter(self))
		agents = self[prim] if breed is None else self[prim][breed]
		if not good: data = pandas.Series([getattr(a, var) for a in agents]) #Pandas gives us nice statistical functions
		else: data = pandas.Series([a.stocks[var] for a in agents])
		stats = {
			'n': data.size,
			'Mean': data.mean(),
			'StDev': data.std(),
			'Variance': data.var(),
			'Maximum': data.max(),
			'Minimum': data.min(),
			'Sum': data.sum()
		}
		for k, v in stats.items():
			print(k+': ', v)

	#Deprecated in Helipad 1.6, remove in Helipad 1.8
	def add(self, *args, **kwargs):
		"""Add a primitive. This method is deprecated; use `model.agents.addPrimitive()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.primitives.add', 'model.agents.addPrimitive'), FutureWarning, 2)
		self.addPrimitive(*args, **kwargs)

	#Deprecated in Helipad 1.6, remove in Helipad 1.8
	def remove(self, name):
		"""Remove a primitive. This method is deprecated; use `model.agents.removePrimitive()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.primitives.remove', 'model.agents.removePrimitive'), FutureWarning, 2)
		self.removePrimitive(name)

class Primitive(list):
	"""List-like container for agents of a primitive, plus data defining that primitive. Stored within the `Agents` object. https://helipad.dev/functions/primitive/"""
	def __init__(self, **kwargs):
		for k,v in kwargs.items(): setattr(self, k, v)
		super().__init__()

	def __getitem__(self, val):
		if isinstance(val, str): return [a for a in self if a.breed==val]
		else: return super().__getitem__(val)

class gandb(funcStore):
	"""Base class for breeds and goods containers. Should not be called directly"""
	def __init__(self, model):
		self.model = model

	def add(self, obj: str, name: str, color, **kwargs):
		"""Add an item."""
		if name in self:
			warnings.warn(ï('{0} \'{1}\' already defined. Overriding…').format(obj, name), None, 2)

		cobj = color if isinstance(color, Color) else Color(color)
		cobj2 = cobj.lighten()
		self[name] = Item(color=cobj, color2=cobj2, **kwargs)

		#Make sure the parameter lists keep up with our items
		if obj=='good': paramDict = self.model.params.perGood
		elif obj=='breed': paramDict = {k:v for k,v in self.model.params.perBreed.items() if v.prim==self.primitive}
		for p in paramDict.values(): p.addKey(name)

		return self[name]

	def remove(self, name: str):
		"""Remove an item."""
		if isinstance(name, (list, tuple)): return [self.remove(n) for n in name]
		if not name in self: return False

		#Also delete per-item parameters
		pdict = self.model.params.perBreed if isinstance(self, Breeds) else self.model.params.perGood
		for param in pdict.values():
			del param.value[name]
			if getattr(param, 'elements', False):
				if not isNotebook(): param.elements[name].destroy()
				else: param.elements[name].close()
				del param.elements[name]
		return super().remove(name)

class Breeds(gandb):
	"""Interface for adding and storing data on breeds. Stored within the `Primitive` object. https://helipad.dev/functions/breeds/"""
	def __init__(self, model, primitive: str):
		self.primitive = primitive
		super().__init__(model)

	def add(self, name: str, color):
		"""Register an agent breed. https://helipad.dev/functions/breeds/add/"""
		return super().add('breed', name, color)

class Edges(MultiDict):
	"""Interface for adding and storing connections between agents that define a network. Stored in `Agent.edges`. https://helipad.dev/functions/edges/"""
	def __init__(self, agent: baseAgent):
		self.agent = agent
		super().__init__()

	def add(self, partner: baseAgent, kind: str='edge', direction=None, weight=1):
		"""Create a network connection between the current agent and `partner`. https://helipad.dev/functions/edges/add/"""
		return Edge(self.agent, partner, kind, direction, weight)

	def outbound(self, kind='edge', undirected: bool=False, obj: str='edge'):
		"""Return a list of edges for which the agent is a startpoint. Undirected edges can be excluded or included with `undirected`. https://helipad.dev/functions/edges/outbound/"""
		if obj not in ['agent', 'edge']: raise ValueError(ï('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.all
		else:
			if kind not in self: return []
			edges = self[kind]
		ob = [edge for edge in edges if edge.startpoint == self.agent or (undirected and not edge.directed)]
		return ob if obj=='edge' else [e.partner(self.agent) for e in ob]

	def inbound(self, kind='edge', undirected: bool=False, obj: str='edge'):
		"""Return a list of edges for which the agent is an endpoint. Undirected edges can be excluded or included with `undirected`. https://helipad.dev/functions/edges/inbound/"""
		if obj not in ['agent', 'edge']: raise ValueError(ï('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.all
		else:
			if kind not in self: return []
			edges = self[kind]
		ib = [edge for edge in edges if edge.endpoint == self.agent or (undirected and not edge.directed)]
		return ib if obj=='edge' else [e.partner(self.agent) for e in ib]

	def With(self, partner: baseAgent, kind='edge'):
		"""Returns a list of direct connections with `partner`. Does not indicate indirect connections. https://helipad.dev/functions/edges/with/"""
		if kind is not None:
			if kind not in self: return []
			edges = self[kind]
		else: edges = self.all
		return [edge for edge in edges if self.agent in edge.vertices and partner in edge.vertices]

class ModelEdges(MultiDict):
	"""Interface for gathering aggregations of connections between agents. Stored in `model.agent.edges`."""
	def __init__(self, agents: Agents):
		self.agents = agents
		super().__init__()

	def __getitem__(self, val): return [e for e in self.all if e.kind==val]
	def __contains__(self, val) -> bool: return val in list(self.keys())
	def items(self): yield from self._dict.items()
	def values(self): yield from self._dict.values()
	def keys(self):
		ks = []
		for e in self.all:
			if not e.kind in ks: ks.append(e.kind)
		yield from ks
	__iter__ = keys
	def __repr__(self): return self._dict.__repr__()

	@property
	def _dict(self):
		es = {}
		for e in self.all:
			if not e.kind in es: es[e.kind] = []
			if not e in es[e.kind]: es[e.kind].append(e)
		return es

	@property
	def all(self) -> list:
		"""A list of all network edges in the model."""
		es = []
		for a in self.agents.all: es += a.edges.all
		return es
