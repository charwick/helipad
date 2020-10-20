#===============
# Unlike other ABM frameworks like Mesa or Netlogo, Helipad is not specifically designed for spatial models.
# However, it can be extended easily enough to do so using networks to create a grid.
# The functions in this module are in pre-beta and not API stable.
#===============

from random import randint
from math import sqrt

#===============
# THE PATCH PRIMITIVE
# Create an agent primitive for the patches
#===============

from helipad.agent import baseAgent
class Patch(baseAgent):
	@property
	def neighbors(self):
		return self.outbound('space', True, obj='agent')
	
	@property
	def up(self):
		if self.y==0 and not self.model.param('wrap'): return None
		return self.model.patches[self.x][self.y-1 if self.y > 0 else self.model.param('y')-1]
	
	@property
	def right(self):
		if self.x>=self.model.param('x')-1 and not self.model.param('wrap'): return None
		return self.model.patches[self.x+1 if self.x < self.model.param('x')-1 else 0][self.y]
	
	@property
	def down(self):
		if self.y>=self.model.param('y')-1 and not self.model.param('wrap'): return None
		return self.model.patches[self.x][self.y+1 if self.y < self.model.param('y')-1 else 0]
	
	@property
	def left(self):
		if self.x==0 and not self.model.param('wrap'): return None
		return self.model.patches[self.x-1 if self.x > 0 else self.model.param('x')-1][self.y]
	
	@property
	def agentsOn(self):
		for prim, lst in self.model.agents.items():
			if prim=='patch': continue
			yield from [a for a in lst if a.x==self.x and a.y==self.y]

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
	
	model.addPrimitive('patch', Patch, hidden=True)
	model.addParameter('square', 'Square', 'hidden', dflt=square)
	model.addParameter('wrap', 'Wrap', 'hidden', dflt=wrap) #Only checked at the beginning of a model
	
	#Hook a positioning function or randomly position our agents
	@model.hook(prioritize=True)
	def baseAgentInit(agent, model):
		if agent.primitive == 'patch': return #Patch position is fixed
		p = model.doHooks(['baseAgentPosition', agent.primitive+'Position'], [agent, agent.model])
		agent.position = list(p) if p and len(p) >= 2 else [randint(0, model.param('x')-1), randint(0, model.param('y')-1)]
	
	#Both agents and patches to have x and y properties
	baseAgent.x = property(lambda self: self.position[0])
	baseAgent.y = property(lambda self: self.position[1])
	
	def distanceFrom(self, agent2):
		return sqrt((self.x-agent2.x)**2 + (self.y-agent2.y)**2)
	baseAgent.distanceFrom = distanceFrom
	
	#MOVEMENT AND POSITION
	
	#Functions for all primitives except patches, which are spatially fixed
	def NotPatches(function):
		def np2(self, *args, **kwargs):
			if self.primitive != 'patch': function(self, *args, **kwargs)
			else: raise RuntimeError('Patches cannot move.')
		return np2
	
	baseAgent.patch = property(lambda self: self.model.patches[self.x][self.y])
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
			if self.position[0] > mapx-1: self.position[0] = mapx-1
			elif self.position[0] < 0: self.position[0] = 0
			if self.position[1] > mapy-1: self.position[1]=mapy-1
			elif self.position[1] < 0: self.position[1] = 0
		else:
			if self.position[0] > mapx-1:
				while self.position[0] > mapx-1: self.position[0] -= mapx
			elif self.position[0] < 0:
				while self.position[0] < 0: self.position[0] += mapx
			if self.position[1] > mapy-1:
				while self.position[1] > mapy-1: self.position[1] -= mapy
			elif self.position[1] < 0:
				while self.position[1] < 0: self.position[1] += mapy

	baseAgent.move = NotPatches(move)
	def moveTo(self, x, y):
		if x>=self.model.param('x') or y>=self.model.param('y'): raise IndexError('Dimension is out of range.')
		self.position = [x,y]
	baseAgent.moveTo = NotPatches(moveTo)
	
	#Position our patches so we can get them with model.patches[x][y]
	@model.hook(prioritize=True)
	def patchInit(agent, model):
		x=0
		while len(model.patches[x]) >= model.param('y'): x+=1	#Find a column that's not full yet
		agent.position = (x, len(model.patches[x]))				#Note the position
		model.patches[x].append(agent)							#Append the agent

	@model.hook(prioritize=True)
	def modelPreSetup(model):
		model.patches = [[] for i in range(model.param('x'))]
		model.param('num_patch', model.param('x')*model.param('y'))
	
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