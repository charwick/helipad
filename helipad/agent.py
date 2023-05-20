# ==========
# Basic extensible agent class
# Do not run this file; import model.py and run from your file.
# ==========

import warnings
from random import choice, randint, shuffle
from math import degrees, radians, pi
import numpy as np
import pandas
from helipad.helpers import ï, funcStore, Color, Item

#Basic agent functions. This class should not be instantiated directly; instead it should be
#subclassed by a class corresponding to a primitive and registered with Helipad.addPrimitive().
#See below, the Agent() class for a minimal example.
class baseAgent:
	angleUnit = 'deg'
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
		self.edges = Edges(self)
		self.utils = 0
		self.position = None #Overridden in spatial init
		self.currentDemand = {g:0 for g in model.goods.keys()}
		self.rads = 0

		#For multi-level models
		#Has to be a static property since we're checking as the object initializes
		if hasattr(super(), 'runInit'): super().__init__()

		self.model.doHooks(['baseAgentInit', self.primitive+'Init'], [self, self.model])

	def __repr__(self): return f'<{self.__class__.__name__} {self.id}>'

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

	#Price is per-unit
	#Returns the quantity actually sold, Which is the same as quantity input unless there's a shortage
	def buy(self, partner, good, q, p):
		if self.model.goods.money is None: raise RuntimeError(ï('{} requires a monetary good to be specified.').format('Agent.buy()'))
		qp = self.model.doHooks('buy', [self, partner, good, q, p])
		if qp is not None: q, p = qp

		before = self.stocks[good]
		self.trade(partner, self.model.goods.money, p*q, good, q)
		return self.stocks[good] - before

	#Unilateral
	def pay(self, recipient, amount):
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
		if self.model.goods.money is None: raise RuntimeError(ï('Balance checking requires a monetary good to be specified.'))
		bal = self.stocks[self.model.goods.money]
		bal_ = self.model.doHooks('checkBalance', [self, bal, self.model])
		if bal_ is not None: bal = bal_

		return bal

	#==================
	# GENETIC METHODS
	#==================

	def reproduce(self, inherit=[], mutate={}, partners=[]):
		if self.fixed: raise NotImplementedError(ï('Fixed primitives cannot reproduce.'))

		maxid = 0
		for a in self.model.agents.all:
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
			else: raise ValueError(ï('Invalid statistic {}.').format(stat))

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
			p.edges.add(newagent,'lineage', True) #Keep track of parent-child relationships
		self.model.agents[self.primitive].append(newagent)

		self.model.doHooks(['baseAgentReproduce', self.primitive+'Reproduce'], [parents, newagent, self.model])
		return newagent

	def die(self, updateGUI=True):
		if self.fixed: raise NotImplementedError(ï('Fixed primitives cannot die.'))
		self.model.agents[self.primitive].remove(self)
		for edge in self.edges.all: edge.cut()
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
	# All deprecated in Helipad 1.6, remove in Helipad 1.8
	#==================

	def newEdge(self, partner, kind='edge', direction=None, weight=1):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.newEdge()', 'Agent.edges.add()'), FutureWarning, 2)
		return self.edges.add(partner, kind, direction, weight)

	def outbound(self, kind='edge', undirected=False, obj='edge'):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.outbound()', 'Agent.edges.outbound()'), FutureWarning, 2)
		return self.edges.outbound(kind, undirected, obj)

	def inbound(self, kind='edge', undirected=False, obj='edge'):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.inbound()', 'Agent.edges.inbound()'), FutureWarning, 2)
		return self.edges.inbound(kind, undirected, obj)

	def edgesWith(self, partner, kind='edge'):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.edgesWith()', 'Agent.edges.With()'), FutureWarning, 2)
		return self.edges.With(partner, kind)

	@property
	def alledges(self):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('Agent.allEdges', 'Agent.edges.all'), FutureWarning, 2)
		return self.edges.all

	#==================
	# OTHER METHODS
	#==================

	#Agent.orientation reports and sets degrees or radians, depending on Agent.angleUnit.
	#Agent.rads always reports radians and is not documented.
	@property
	def orientation(self):
		if self.primitive == 'patch': return None
		return degrees(self.rads) if 'deg' in self.angleUnit else self.rads

	@orientation.setter
	def orientation(self, val):
		if self.primitive == 'patch': raise RuntimeError(ï('Patches cannot rotate.'))
		if 'deg' in self.angleUnit: val = radians(val)
		while val >= 2*pi: val -= 2*pi
		while val < 0: val += 2*pi
		self.rads = val

	def rotate(self, angle): self.orientation += angle

	@property
	def patch(self):
		if self.position is not None: return self.model.patches.at(*self.position)

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

	#Don't remove from the list; just mark as dead
	def die(self):
		self.dead = True
		if not self.model.patches.offmap:
			for a in self.agentsOn: a.die()
		self.model.doHooks(['baseAgentDie', 'PatchDie'], [self])

	@property
	def neighbors(self):
		return [p for p in self.edges.outbound('space', True, obj='agent') if not p.dead]

	def __repr__(self): return f'<Patch at {self.position[0]},{self.position[1]}>'

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
		for agent in self.vertices:
			if self in agent.edges[self.kind]: agent.edges[self.kind].remove(self) #Remove from agents
		self.active = False
		self.vertices[0].model.doHooks('edgeCut', [self])

	def partner(self, agent):
		if agent==self.vertices[0]: return self.vertices[1]
		elif agent==self.vertices[1]: return self.vertices[0]
		else: raise ValueError(ï('Agent {} is not connected to this edge.').format(agent.id))

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

#==================
# CONTAINER CLASSES
#==================

#Basic methods for a dict of dicts
class MultiDict(dict):
	def __len__(self):
		return sum([len(a) for a in self])

	@property
	def all(self):
		agents = []
		for l in self.values(): agents += l
		return agents

class Agents(MultiDict):
	def __init__(self, model):
		self.model = model
		self.order = 'linear'
		super().__init__()

	#Allow retrieval by either primitive or agent ID
	def __getitem__(self, val):
		if isinstance(val, int):
			for p in super().values():
				for a in p:
					if a.id==val: return a
		else: return super().__getitem__(val)

	#Act as if we've sorted by priority when looping
	def items(self): yield from sorted(super().items(), key=lambda d: d[1].priority)
	def values(self): yield from sorted(super().values(), key=lambda d: d.priority)
	def keys(self): yield from [k[0] for k in sorted(super().items(), key=lambda d: d[1].priority)]
	__iter__ = keys

	def addPrimitive(self, name, class_, plural=None, dflt=50, low=1, high=100, step=1, hidden=False, priority=100, order=None):
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
		def popget(name, model):
			prim = name.split('_')[1]
			if not model.hasModel: return None
			else: return len(model.agents[prim])

		self.model.params.add('num_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step} if not hidden else None, setter=self.initialize, getter=popget)

	def removePrimitive(self, name):
		del self[name]
		del self.model.params['num_'+name]

	def addBreed(self, name, color, prim=None):
		if prim is None:
			if len(super().keys()) == 1: prim = next(iter(self.keys()))
			else: raise KeyError(ï('Breed must specify which primitive it belongs to.'))
		return self[prim].breeds.add(name, color)

	#Creates an unweighted and undirected network of a certain density
	def createNetwork(self, density, kind='edge', prim=None):
		if density < 0 or density > 1: raise ValueError(ï('Network density must take a value between 0 and 1.'))
		from itertools import combinations
		agents = self.all if prim is None else self[prim]
		for c in combinations(agents, 2):
			if np.random.randint(0,100) < density*100:
				c[0].edges.add(c[1], kind)
		return self.network(kind, prim)

	def network(self, kind='edge', prim=None, excludePatches=False):
		import networkx as nx

		#Have to use DiGraph in order to draw any arrows
		G = nx.DiGraph(name=kind)
		agents = list(self.all) if prim is None else self[prim]
		if excludePatches: agents = [a for a in agents if a.primitive!='patch']
		G.add_nodes_from([(a.id, {'breed': a.breed, 'primitive': a.primitive, 'position': None if a.position is None else a.position.copy()}) for a in agents])
		ae = self.allEdges
		if kind in ae:
			for e in ae[kind]:
				if prim is None or (e.vertices[0].primitive==prim and e.vertices[1].primitive==prim): G.add_edge(
					e.startpoint.id if e.directed else e.vertices[0].id,
					e.endpoint.id if e.directed else e.vertices[1].id,
					weight=e.weight, directed=e.directed
				)
		return G

	#CALLBACK FOR DEFAULT PARAMETERS
	#Model param redundant, strictly speaking, but it's necessary to make the signature match the setter callback
	def initialize(self, val, prim, model=None, force=False):
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
	def summary(self, var, prim=None, breed=None, good=False):
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

	@property
	def allEdges(self):
		es = {}
		for a in self.all:
			for e in a.edges.all:
				if not e.kind in es: es[e.kind] = []
				if not e in es[e.kind]: es[e.kind].append(e)
		return es

	#Deprecated in Helipad 1.6, remove in Helipad 1.8
	def add(self, *args, **kwargs):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.primitives.add', 'model.agents.addPrimitive'), FutureWarning, 2)
		self.addPrimitive(*args, **kwargs)

	#Deprecated in Helipad 1.6, remove in Helipad 1.8
	def remove(self, name):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.primitives.remove', 'model.agents.removePrimitive'), FutureWarning, 2)
		self.removePrimitive(name)

class Primitive(list):
	def __init__(self, **kwargs):
		for k,v in kwargs.items(): setattr(self, k, v)
		super().__init__()

	def __getitem__(self, val):
		if isinstance(val, str): return [a for a in self if a.breed==val]
		else: return super().__getitem__(val)

#For adding breeds and goods. Should not be called directly
class gandb(funcStore):
	def __init__(self, model):
		self.model = model

	def add(self, obj, name, color, prim=None, **kwargs):
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

	def remove(self, name):
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
	def __init__(self, model, primitive):
		self.primitive = primitive
		super().__init__(model)

	def add(self, name, color): return super().add('breed', name, color)

class Edges(MultiDict):
	def __init__(self, agent):
		self.agent = agent
		super().__init__()

	def add(self, partner, kind='edge', direction=None, weight=1):
		return Edge(self.agent, partner, kind, direction, weight)

	def outbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError(ï('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.all
		else:
			if kind not in self: return []
			edges = self[kind]
		ob = [edge for edge in edges if edge.startpoint == self.agent or (undirected and not edge.directed)]
		return ob if obj=='edge' else [e.partner(self.agent) for e in ob]

	def inbound(self, kind='edge', undirected=False, obj='edge'):
		if obj not in ['agent', 'edge']: raise ValueError(ï('Object must be specified either \'agent\' or \'edge\'.'))
		if kind is None: edges = self.all
		else:
			if kind not in self: return []
			edges = self[kind]
		ib = [edge for edge in edges if edge.endpoint == self.agent or (undirected and not edge.directed)]
		return ib if obj=='edge' else [e.partner(self.agent) for e in ib]

	def With(self, partner, kind='edge'):
		if kind is not None:
			if kind not in self: return []
			edges = self[kind]
		else: edges = self.all
		return [edge for edge in edges if self.agent in edge.vertices and partner in edge.vertices]