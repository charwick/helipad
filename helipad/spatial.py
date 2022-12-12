#===============
# Functions to initialize a grid network of Patch agents
# and add orientation and motion functions to other agents.
#===============

import warnings
from random import randint
from math import sqrt, degrees, radians, sin, cos, atan2, pi
from helipad.agent import Patch, baseAgent
from helipad.visualize import Charts
from helipad.helpers import ï

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
	model.params.add('wrap', ï('Wrap'), 'hidden', dflt=wrap) #Only checked at the beginning of a model
	
	pClasses = {'rect': PatchesRect}
	def npsetter(val, item): raise RuntimeError(ï('Patch number cannot be set directly. Set the dim parameter instead.'))
	model.params['num_patch'].getter = lambda item: model.patches.count if getattr(model, 'patches', False) else 0
	model.params['num_patch'].setter = npsetter

	#Hook a positioning function or randomly position our agents
	@model.hook(prioritize=True)
	def baseAgentInit(agent, model):
		if agent.primitive == 'patch': return #Patch position is fixed
		p = model.doHooks(['baseAgentPosition', agent.primitive+'Position'], [agent, agent.model])
		agent.position = list(p) if p and len(p) >= 2 else [randint(0, model.param('x')-1), randint(0, model.param('y')-1)]
		agent.rads = 0

	#MOVEMENT AND POSITION

	#Both agents and patches have x and y properties
	def setx(self, val): self.moveTo(val, self.position[1])
	def sety(self, val): self.moveTo(self.position[0], val)
	baseAgent.x = property(lambda self: self.position[0], setx)
	baseAgent.y = property(lambda self: self.position[1], sety)

	def distanceFrom(self, agent2):
		return sqrt((self.x-agent2.x)**2 + (self.y-agent2.y)**2)
	baseAgent.distanceFrom = distanceFrom

	baseAgent.patch = property(lambda self: self.model.patches[round(self.x), round(self.y)])
	def move(self, x, y):
		mapx, mapy, wrap = self.model.param('x'), self.model.param('y'), self.model.param('wrap')
		self.position[0] += x
		self.position[1] += y
		if not wrap:
			self.position[0] = min(self.position[0], mapx-0.5)
			self.position[0] = max(self.position[0], -0.5)
			self.position[1] = min(self.position[1], mapy-0.5)
			self.position[1] = max(self.position[1], -0.5)
		else:
			while self.position[0] >= mapx-0.5: self.position[0] -= mapx
			while self.position[0] < -0.5: self.position[0] += mapx
			while self.position[1] >= mapy-0.5: self.position[1] -= mapy
			while self.position[1] < -0.5: self.position[1] += mapy
	baseAgent.move = NotPatches(move)

	#Can also take an agent or patch as a single argument
	def moveTo(self, x, y=None):
		if type(x) not in [int, float]: x,y = x.position
		if x>self.model.param('x')+0.5 or y>self.model.param('y')+0.5 or x<-0.5 or y<-0.5: raise IndexError('Dimension is out of range.')
		self.position = [x,y]
	baseAgent.moveTo = NotPatches(moveTo)

	#ANGLE FUNCTIONS

	#Agent.orientation reports and sets degrees or radians, depending on Agent.angle.
	#Agent.rads always reports radians and is not documented.
	def orientation(self): return degrees(self.rads) if 'deg' in self.angle else self.rads
	def setOrientation(self, val):
		if 'deg' in self.angle: val = radians(val)
		while val >= 2*pi: val -= 2*pi
		while val < 0: val += 2*pi
		self.rads = val
	baseAgent.orientation = property(NotPatches(orientation), NotPatches(setOrientation))

	def rotate(self, angle): self.orientation += angle
	baseAgent.rotate = NotPatches(rotate)

	def orientTo(self, x, y=None):
		if not isinstance(x, int): x,y = x.position
		difx, dify = x-self.x, y-self.y
		if self.model.param('wrap'):
			dimx, dimy = self.model.param('x'), self.model.param('y')
			if difx>dimx/2: difx -= dimx
			elif difx<-dimx/2: difx += dimx
			if dify>dimy/2: dify -= dimy
			elif dify<-dimy/2: dify += dimy

		self.rads = atan2(dify,difx) + 0.5*pi #atan calculates 0º pointing East. We want 0º pointing North
	baseAgent.orientTo = NotPatches(orientTo)

	def forward(self, steps=1):
		self.move(steps * cos(self.rads-90), steps * sin(self.rads-90))
	baseAgent.forward = NotPatches(forward)

	#Initialize the patch container at the beginning of the model
	@model.hook(prioritize=True)
	def modelPreSetup(model):
		model.patches = pClasses[shape](model.param('x'), model.param('y'))

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

	mapPlot = model.visual.addPlot('map', 'Map', type='network', layout='patchgrid')
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
	def __init__(self, x, y):
		self.x, self.y = x, y
		super().__init__([[] for i in range(x)])
	
	def __getitem__(self, key):
		if isinstance(key, int): return super().__getitem__(key)
		else: return super().__getitem__(key[0])[key[1]]

	def __setitem__(self, key, val):
		if isinstance(key, int): return super().__setitem__(key, val)
		else: super().__getitem__(key[0])[key[1]] = val

#Each row and column of equal length
class PatchesRect(Patches2D):
	shape = 'rect'

	#Give patches and agents methods for their neighbors in the four cardinal directions
	def __init__(self, x, y):
		super().__init__(x, y)

		def up(patch):
			if patch.y==0 and not patch.model.param('wrap'): return None
			return self[patch.x, patch.y-1 if patch.y > 0 else patch.model.param('y')-1]
		Patch.up = property(up)

		def right(patch):
			if patch.x>=patch.model.param('x')-1 and not patch.model.param('wrap'): return None
			return self[self.x+1 if self.x < patch.model.param('x')-1 else 0, patch.y]
		Patch.right = property(right)

		def down(patch):
			if patch.y>=patch.model.param('y')-1 and not patch.model.param('wrap'): return None
			return self[patch.x, patch.y+1 if patch.y < patch.model.param('y')-1 else 0]
		Patch.down = property(down)

		def left(patch):
			if patch.x==0 and not patch.model.param('wrap'): return None
			return self[patch.x-1 if patch.x > 0 else patch.model.param('x')-1, patch.y]
		Patch.left = property(left)
		
		def moveUp(agent): agent.move(0, -1)
		baseAgent.moveUp = NotPatches(moveUp)
		def moveRight(agent): agent.move(1, 0)
		baseAgent.moveRight = NotPatches(moveRight)
		def moveDown(agent): agent.move(0, 1)
		baseAgent.moveDown = NotPatches(moveDown)
		def moveLeft(agent): agent.move(-1, 0)
		baseAgent.moveLeft = NotPatches(moveLeft)

	def neighbors(self, patch, corners):
		neighbors = [(patch.up, 1), (patch.right, 1), (patch.down, 1), (patch.left, 1)]
		if corners: neighbors += [(patch.up.left, corners), (patch.right.up, corners), (patch.down.right, corners), (patch.left.down, corners)]
		return [p for p in neighbors if p[0] is not None]

	#Take a sequential list of self.count patches and position them appropriately in the internal list
	def place(self, agent):
		x=0
		while len(self[x]) >= self.y: x+=1		#Find a column that's not full yet
		agent.position = (x, len(self[x]))		#Note the position
		self[x].append(agent)					#Append the agent

	@property
	def count(self): return self.x * self.y