#===============
# Unlike other ABM frameworks like Mesa or Netlogo, Helipad is not specifically designed for spatial models.
# However, it can be extended easily enough to do so using networks to create a grid.
# The functions in this module are in pre-beta and not API stable.
#===============

from helipad.agent import Patch, baseAgent
from random import randint
from math import sqrt, degrees, radians, sin, cos, atan2, pi
import pandas

#===============
# SETUP
# Create parameters, add functions, and so on
#===============

def spatialSetup(model, square=None, x=10, y=None, wrap=True, diag=False):
	
	#Dimension parameters
	#If square, have the x and y parameters alias dimension
	if square is None: square = not bool(y) #If y wasn't specified, assume user wants a square
	if square:
		model.addParameter('dimension', 'Map Size', 'slider', dflt=x, opts={'low': 1, 'high': x, 'step': 1}, runtime=False)
		def dimget(name, model): return model.param('dimension')
		def dimset(val, name, model): model.param('dimension', val)
		model.addParameter('x', 'Map Width ', 'hidden', dflt=x, setter=dimset, getter=dimget)
		model.addParameter('y', 'Map Height', 'hidden', dflt=x, setter=dimset, getter=dimget)
	else:
		model.addParameter('x', 'Map Width ', 'slider', dflt=x, opts={'low': 1, 'high': x, 'step': 1}, runtime=False)
		model.addParameter('y', 'Map Height', 'slider', dflt=y, opts={'low': 1, 'high': y, 'step': 1}, runtime=False)
	
	model.addPrimitive('patch', Patch, hidden=True, priority=-10)
	model.addParameter('square', 'Square', 'hidden', dflt=square)
	model.addParameter('wrap', 'Wrap', 'hidden', dflt=wrap) #Only checked at the beginning of a model
	
	def npsetter(val, item): raise RuntimeError('Patch number cannot be set directly. Set the x and y parameters instead.')
	model.params['num_patch'].getter = lambda item: model.param('x')*model.param('y')
	model.params['num_patch'].setter = npsetter
	
	#Hook a positioning function or randomly position our agents
	@model.hook(prioritize=True)
	def baseAgentInit(agent, model):
		if agent.primitive == 'patch': return #Patch position is fixed
		p = model.doHooks(['baseAgentPosition', agent.primitive+'Position'], [agent, agent.model])
		agent.position = list(p) if p and len(p) >= 2 else [randint(0, model.param('x')-1), randint(0, model.param('y')-1)]
		agent.angle = 0
	
	#MOVEMENT AND POSITION
	
	#Functions for all primitives except patches, which are spatially fixed
	def NotPatches(function):
		def np2(self, *args, **kwargs):
			if self.primitive != 'patch': return function(self, *args, **kwargs)
			else: raise RuntimeError('Patches cannot move.')
		return np2
	
	def setx(self, val): self.position[0] = val
	def sety(self, val): self.position[1] = val
	
	#Both agents and patches to have x and y properties
	baseAgent.x = property(lambda self: self.position[0], setx)
	baseAgent.y = property(lambda self: self.position[1], sety)
	
	def distanceFrom(self, agent2):
		return sqrt((self.x-agent2.x)**2 + (self.y-agent2.y)**2)
	baseAgent.distanceFrom = distanceFrom
	
	baseAgent.patch = property(lambda self: self.model.patches[round(self.x), round(self.y)])
	def moveUp(self): self.position = list(self.patch.up.position)
	baseAgent.moveUp = NotPatches(moveUp)
	def moveRight(self): self.position = list(self.patch.right.position)
	baseAgent.moveRight = NotPatches(moveRight)
	def moveDown(self): self.position = list(self.patch.down.position)
	baseAgent.moveDown = NotPatches(moveDown)
	def moveLeft(self): self.position = list(self.patch.left.position)
	baseAgent.moveLeft = NotPatches(moveLeft)
	def move(self, x, y):
		mapx, mapy, wrap = self.model.param('x'), self.model.param('y'), self.model.param('wrap')
		self.position[0] += x
		self.position[1] += y
		if not wrap:
			if self.position[0] > mapx-0.5: self.position[0] = mapx-0.5
			elif self.position[0] < -0.5: self.position[0] = -0.5
			if self.position[1] > mapy-0.5: self.position[1]=mapy-0.5
			elif self.position[1] < -0.5: self.position[1] = -0.5
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
	
	def orientation(self): return self.angle
	def setOrientation(self, val):
		self.angle = val
		while self.angle >= 360: self.angle -= 360
		while self.angle < 0: self.angle += 360
	baseAgent.orientation = property(NotPatches(orientation), NotPatches(setOrientation))
	
	def rotate(self, angle): self.orientation += angle
	baseAgent.rotate = NotPatches(rotate)
	
	def orientTo(self, x, y=None):
		if type(x) is not int: x,y = x.position
		difx, dify = x-self.x, y-self.y
		if self.model.param('wrap'):
			dimx, dimy = self.model.param('x'), self.model.param('y')
			if difx>dimx/2: difx -= dimx
			elif difx<-dimx/2: difx += dimx
			if dify>dimy/2: dify -= dimy
			elif dify<-dimy/2: dify += dimy
		
		rads = atan2(dify,difx) + 0.5*pi #atan calculates 0º pointing East. We want 0º pointing North
		self.orientation = degrees(rads)
	baseAgent.orientTo = NotPatches(orientTo)
	
	def forward(self, steps=1):
		self.move(steps * cos(radians(self.orientation-90)), steps * sin(radians(self.orientation-90)))
	baseAgent.forward = NotPatches(forward)
	
	#A 2D list that lets us use [x,y] indices
	class Patches(list):
		def __getitem__(self, key):
			if type(key) is int: return super().__getitem__(key)
			else: return super().__getitem__(key[0])[key[1]]
	
		def __setitem__(self, key, val):
			if type(key) is int: return super().__setitem__(key, val)
			else: super().__getitem__(key[0])[key[1]] = val
	
	#Position our patches in a 2D array
	@model.hook(prioritize=True)
	def patchInit(agent, model):
		x=0
		while len(model.patches[x]) >= model.param('y'): x+=1	#Find a column that's not full yet
		agent.position = (x, len(model.patches[x]))				#Note the position
		model.patches[x].append(agent)							#Append the agent
		agent.colorData = {}

	@model.hook(prioritize=True)
	def modelPreSetup(model):
		model.patches = Patches([[] for i in range(model.param('x'))])
	
	#Establish grid links
	@model.hook(prioritize=True)
	def modelPostSetup(model):
		for patch in model.agents['patch']:
			neighbors = [ patch.up, patch.right, patch.down, patch.left ]
			connections = patch.neighbors #Neighbors that already have a connection
			for n in neighbors:
				if n and not n in connections:
					patch.newEdge(n, 'space')
		
			if diag:
				for d in [patch.up.left, patch.right.up, patch.down.right, patch.left.down]:
					if d and not d in connections:
						patch.newEdge(d, 'space', weight=float(diag))
	
	#Don't reset the visualizer if charts is already registered
	from helipad.visualize import Charts
	if not hasattr(model, 'visual') or type(model.visual) is not Charts:
		model.useVisual(Charts)
	
	mapPlot = model.visual.addPlot('map', 'Map', type='network', layout='patchgrid')
	return mapPlot