#===============
# Functions to initialize a grid network of Patch agents
# and add orientation and motion functions to other agents.
#===============

import warnings
from random import randint
from math import sqrt, sin, cos, atan2, pi, copysign, floor
from helipad.agent import Patch, baseAgent
from helipad.visualize import Charts
from helipad.helpers import ï, Number

#===============
# SETUP
# Create parameters, add functions, and so on
#===============

def spatialSetup(model, dim=10, wrap=True, corners=False, shape='rect', **kwargs):
	# Backward compatibility
	if 'x' in kwargs:		#Remove in Helipad 1.6
		dim = kwargs['x'] if 'y' not in kwargs else (kwargs['x'], kwargs['y'])
		warnings.warn(ï('Using x and y to set dimensions is deprecated. Use the dim argument instead.'), FutureWarning, 3)
	if 'diag' in kwargs:	#Remove in Helipad 1.7
		corners = kwargs['diag']
		warnings.warn(ï('The `diag` argument is deprecated. Use the `corners` argument instead.'), FutureWarning, 3)

	#Dimension parameters
	#If equidimensional, have the x and y parameters alias dimension
	if isinstance(dim, int):
		model.params.add('dimension', ï('Map Size'), 'slider', dflt=dim, opts={'low': 1, 'high': dim, 'step': 1}, runtime=False)
		def dimget(name, model): return model.param('dimension')
		def dimset(val, name, model): model.param('dimension', val)
		model.params.add('x', ï('Map Width'), 'hidden', dflt=dim, setter=dimset, getter=dimget)
		model.params.add('y', ï('Map Height'), 'hidden', dflt=dim, setter=dimset, getter=dimget)
	elif isinstance(dim, (list, tuple)):
		model.params.add('x', ï('Map Width'), 'slider', dflt=dim[0], opts={'low': 1, 'high': dim[0], 'step': 1}, runtime=False)
		model.params.add('y', ï('Map Height'), 'slider', dflt=dim[1], opts={'low': 1, 'high': dim[1], 'step': 1}, runtime=False)
	else: raise TypeError(ï('Invalid dimension.'))

	model.primitives.add('patch', Patch, hidden=True, priority=-10)
	model.params.add('square', ï('Square'), 'hidden', dflt=isinstance(dim, (list, tuple)))
	if shape=='polar': wrap='x'
	model.params.add('wrapx', ï('Wrap')+' X', 'hidden', dflt=(wrap is True or wrap=='x')) #Only checked at the beginning of a model
	model.params.add('wrapy', ï('Wrap')+' Y', 'hidden', dflt=(wrap is True or wrap=='y'))

	pClasses = {'rect': PatchesRect, 'polar': PatchesPolar}
	def npsetter(val, item): raise RuntimeError(ï('Patch number cannot be set directly. Set the dim parameter instead.'))
	model.params['num_patch'].getter = lambda item: len(model.patches)
	model.params['num_patch'].setter = npsetter

	#Hook a positioning function or randomly position our agents
	@model.hook(prioritize=True)
	def baseAgentInit(agent, model):
		if agent.primitive == 'patch': return #Patch position is fixed
		p = model.doHooks(['baseAgentPosition', agent.primitive+'Position'], [agent, agent.model])
		agent.position = list(p) if p and len(p) >= 2 else [randint(0, model.param('x')-1), randint(0, model.param('y')-1)]

	#MOVEMENT AND POSITION

	#Both agents and patches have x and y properties
	def setx(self, val): self.moveTo(val, self.position[1])
	def sety(self, val): self.moveTo(self.position[0], val)
	baseAgent.x = property(lambda self: self.position[0], setx)
	baseAgent.y = property(lambda self: self.position[1], sety)

	def move(self, x, y):
		mapx, mapy = self.model.param('x'), self.model.param('y')
		xlim, ylim = self.model.patches.boundaries
		self.position[0] += x
		self.position[1] += y

		if self.model.param('wrapx'):
			while self.position[0] >= xlim[1]: self.position[0] -= mapx
			while self.position[0] < xlim[0]: self.position[0] += mapx
		else:
			self.position[0] = min(self.position[0], xlim[1])
			self.position[0] = max(self.position[0], xlim[0])

		if self.model.param('wrapy'):
			while self.position[1] >= ylim[1]: self.position[1] -= mapy
			while self.position[1] < ylim[0]: self.position[1] += mapy
		else:
			self.position[1] = min(self.position[1], ylim[1])
			self.position[1] = max(self.position[1], ylim[0])

	baseAgent.move = NotPatches(move)

	#Can also take an agent or patch as a single argument
	def moveTo(self, x, y=None):
		if not isinstance(x, Number): x,y = x.position
		if x>self.model.patches.boundaries[0][1] or y>self.model.patches.boundaries[1][1] or x<self.model.patches.boundaries[0][0] or y<self.model.patches.boundaries[1][0]:
			raise IndexError(ï('Dimension is out of range.'))
		self.position = [x,y]
	baseAgent.moveTo = NotPatches(moveTo)

	#Initialize the patch container at the beginning of the model
	@model.hook(prioritize=True)
	def modelPreSetup(model):
		model.patches = pClasses[shape]((model.param('x'), model.param('y')))

	#Position our patches in the coordinate system
	@model.hook(prioritize=True)
	def patchInit(agent, model):
		model.patches.place(agent)
		agent.colorData = {}

	#Establish grid links
	@model.hook(prioritize=True)
	def modelPostSetup(model):
		for patch in model.agents['patch']:
			neighbors = model.patches.neighbors(patch, corners)
			connections = patch.neighbors #Neighbors that already have a connection
			for n, weight in neighbors:
				if not n in connections:
					patch.newEdge(n, 'space', weight=weight)

	#Don't reset the visualizer if charts is already registered
	if not hasattr(model, 'visual') or not isinstance(model.visual, Charts):
		model.useVisual(Charts)

	mapPlot = model.visual.addPlot('map', 'Map', type='network', layout='patchgrid', projection=shape if shape=='polar' else None)
	return mapPlot

#Functions for all primitives except patches, which are spatially fixed
def NotPatches(function):
	def np2(self, *args, **kwargs):
		if self.primitive != 'patch': return function(self, *args, **kwargs)
		else: raise RuntimeError(ï('Patches cannot move.'))
	return np2

#===============
# COORDINATE SYSTEMS
#===============

#A 2D list of lists that lets us use [x,y] indices
class Patches2D(list):
	def __init__(self, dim, props=[], funcs=[]):
		if isinstance(dim, int): dim = (dim, dim)
		if len(dim) != 2: raise TypeError(ï('Invalid dimension.'))
		self.dim = dim
		super().__init__([[] for i in range(dim[0])])

		#Attach coordinate-specific functions and properties to agent objects
		for p in props: setattr(Patch, p.__name__, property(p))
		for f in funcs: setattr(baseAgent, f.__name__, NotPatches(f))

	def __getitem__(self, key):
		if isinstance(key, int): return super().__getitem__(key)
		else:
			if key[1] is None: return super().__getitem__(key[0])
			if key[0] is None: return [x[key[1]] for x in self]
			return super().__getitem__(key[0])[key[1]]

	def __setitem__(self, key, val):
		if isinstance(key, int): return super().__setitem__(key, val)
		else: super().__getitem__(key[0])[key[1]] = val

#Each row and column of equal length
class PatchesRect(Patches2D):
	shape = 'rect'

	#Give patches and agents methods for their neighbors in the four cardinal directions
	def __init__(self, dim):
		def up(patch):
			if patch.y==0 and not patch.model.param('wrapy'): return None
			return self[patch.x, patch.y-1 if patch.y > 0 else self.dim[1]-1]

		def right(patch):
			if patch.x>=patch.model.param('x')-1 and not patch.model.param('wrapx'): return None
			return self[patch.x+1 if patch.x < self.dim[0]-1 else 0, patch.y]

		def down(patch):
			if patch.y>=patch.model.param('y')-1 and not patch.model.param('wrapy'): return None
			return self[patch.x, patch.y+1 if patch.y < self.dim[1]-1 else 0]

		def left(patch):
			if patch.x==0 and not patch.model.param('wrapx'): return None
			return self[patch.x-1 if patch.x > 0 else self.dim[0]-1, patch.y]

		def agentsOn(patch):
			for prim, lst in patch.model.agents.items():
				if prim=='patch': continue
				yield from [a for a in lst if patch.x-0.5<=a.x<patch.x+0.5 and patch.y-0.5<=a.y<patch.y+0.5]

		baseAgent.patch = property(lambda agent: self[round(agent.x), round(agent.y)])

		def moveUp(agent): agent.move(0, -1)
		def moveRight(agent): agent.move(1, 0)
		def moveDown(agent): agent.move(0, 1)
		def moveLeft(agent): agent.move(-1, 0)
		def forward(self, steps=1):
			self.move(steps * cos(self.rads-pi/2), steps * sin(self.rads-pi/2))

		#Internal function  to calculate x,y distances s.t. wrap constraints for distance and orientation purposes
		def _offset(agent, x, y):
			difx, dify = x - agent.x, y - agent.y
			if agent.model.param('wrapx'):
				crossx = difx - copysign(self.dim[0], difx)
				if abs(crossx) < abs(difx): difx = crossx
			if agent.model.param('wrapy'):
				crossy = dify - copysign(self.dim[1], dify)
				if abs(crossy) < abs(dify): dify = crossy
			return (difx, dify)
		baseAgent._offset = _offset

		def distanceFrom(agent, agent2):
			difx, dify = agent._offset(agent2.x, agent2.y)
			return sqrt(difx**2 + dify**2)
		baseAgent.distanceFrom = distanceFrom

		def orientTo(agent, x, y=None):
			if not isinstance(x, Number): x,y = x.position
			difx, dify = agent._offset(x, y)
			agent.rads = atan2(dify,difx) + 0.5*pi #atan calculates 0º pointing East. We want 0º pointing North

		super().__init__(dim, props=[up, right, down, left, agentsOn], funcs=[moveUp, moveRight, moveDown, moveLeft, forward, orientTo])

	def neighbors(self, patch, corners):
		neighbors = [(patch.up, 1), (patch.right, 1), (patch.down, 1), (patch.left, 1)]
		if corners: neighbors += [(patch.up.left, corners), (patch.right.up, corners), (patch.down.right, corners), (patch.left.down, corners)]
		return [p for p in neighbors if p[0] is not None and p[0] is not self]

	#Take a sequential list of self.count patches and position them appropriately in the internal list
	def place(self, agent):
		x=0
		while len(self[x]) >= self.dim[1]: x+=1		#Find a column that's not full yet
		agent.position = (x, len(self[x]))			#Note the position
		self[x].append(agent)						#Append the agent

	@property #((xmin, xmax),(ymin, ymax))
	def boundaries(self): return ((-0.5, self.dim[0]-0.5), (-0.5, self.dim[1]-0.5))

	def __len__(self): return self.dim[0] * self.dim[1]

#x,y placement is the same; just need to redefine patch functions and neighbors
#x is number around, y is number out
class PatchesPolar(PatchesRect):
	shape = 'polar'

	def __init__(self, dim):
		def inward(patch):
			if patch.y==0: return None
			return self[patch.x, patch.y-1]

		def outward(patch):
			if patch.y>=self.dim[1]-1: return None
			return self[patch.x, patch.y+1]

		def clockwise(patch):
			return self[patch.x+1 if patch.x < self.dim[0]-1 else 0, patch.y]

		def counterclockwise(patch):
			return self[patch.x-1 if patch.x > 0 else self.dim[0]-1, patch.y]

		def agentsOn(patch):
			for prim, lst in patch.model.agents.items():
				if prim=='patch': continue
				yield from [a for a in lst if floor(a.x)==patch.x and floor(a.y)==patch.y]

		baseAgent.patch = property(lambda agent: self[floor(agent.x), floor(agent.y)])

		def moveInward(agent): agent.move(0, -1)
		def moveOutward(agent): agent.move(0, 1)
		def moveClockwise(agent): agent.move(1, 0)
		def moveCounterclockwise(agent): agent.move(-1, 0)
		def forward(agent, steps=1):
			#2π-self.rads to make it go clockwise
			th1 = 2*pi-(2*pi/dim[0] * agent.x)
			newth = th1 + atan2(steps*sin(2*pi-agent.rads-th1), agent.y+steps*cos(2*pi-agent.rads-th1))
			newx = (2*pi-newth)/(2*pi/dim[0])
			if newx > dim[0]: newx -= dim[0]
			newr = sqrt(agent.y**2 + steps**2 + 2*agent.y*steps*cos(2*pi-agent.rads-th1))
			agent.move(newx-agent.x, newr-agent.y)

		def distanceFrom(agent, agent2):
			th1 = agent.x * 2*pi / dim[0]
			th2 = agent2.x * 2*pi / dim[0]
			return sqrt(agent.y**2 + agent2.y**2 - 2*agent.y*agent2.y*cos(th1-th2))
		baseAgent.distanceFrom = distanceFrom

		def orientTo(agent, x, y=None):
			if not isinstance(x, Number): x,y = x.position
			th1 = 2*pi-(2*pi/dim[0] * agent.x)
			th2 = 2*pi-(2*pi/dim[0] * x)
			agent.rads = pi - atan2(agent.y * sin(th1) - y * sin(th2), agent.y * cos(th1) - y * cos(th2))

		#Skip PatchesRect.__init__
		Patches2D.__init__(self, dim, props=[inward, outward, clockwise, counterclockwise, agentsOn], funcs=[moveInward, moveOutward, moveClockwise, moveCounterclockwise, forward, orientTo])

	#The usual 3-4 neighbors, but if corners are on, all patches in the center ring will be neighbors
	def neighbors(self, patch, corners):
		neighbors = [(patch.inward, 1), (patch.outward, 1), (patch.clockwise, 1), (patch.counterclockwise, 1)]
		if corners:
			neighbors += [(patch.clockwise.inward, corners), (patch.counterclockwise.inward, corners), (patch.clockwise.outward, corners), (patch.counterclockwise.outward, corners)]
			if patch.y==0:
				flatneighbors = [n[0] for n in neighbors]
				for p in patch.model.patches[None, 0]:
					if p not in flatneighbors:
						neighbors.append((p, corners))

		return [p for p in neighbors if p[0] is not None and p[0] is not self]

	@property #((xmin, xmax),(ymin, ymax))
	def boundaries(self): return ((0, self.dim[0]), (0, self.dim[1]))