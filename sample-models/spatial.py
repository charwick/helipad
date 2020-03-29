# Unlike other ABM frameworks like Mesa or Netlogo, Helipad is not specifically designed for spatial models.
# However, it can be extended easily enough to do so using networks to create a grid.

#===============
# SETUP
# Instantiate the object and add parameters, breeds, and goods below.
#===============

from helipad import *
from random import randint
from math import sqrt

heli = Helipad()
heli.name = 'Spatial Sample'
heli.order = 'random'
heli.addParameter('dimension', 'Dimension', 'slider', dflt=10, opts={'low': 5, 'high': 20, 'step': 1})

#===============
# THE PATCH PRIMITIVE
# Create an agent primitive for the patches
#===============

class Patch(baseAgent):
	@property
	def neighbors(self):
		return self.outbound('space', True, obj='agent')
	
	@property
	def up(self):
		return self.model.patches[self.x][self.y-1 if self.y > 0 else self.model.param('dimension')-1]
	
	@property
	def right(self):
		return self.model.patches[self.x+1 if self.x < self.model.param('dimension')-1 else 0][self.y]
	
	@property
	def down(self):
		return self.model.patches[self.x][self.y+1 if self.y < self.model.param('dimension')-1 else 0]
	
	@property
	def left(self):
		return self.model.patches[self.x-1 if self.x > 0 else self.model.param('dimension')-1][self.y]
	
	@property
	def agentsOn(self):
		return [a for a in self.model.agents['agent'] if a.x==self.x and a.y==self.y]
	
heli.addPrimitive('patch', Patch, hidden=True)

#===============
# BEHAVIOR
#===============

def distance(agent1, agent2):
	return sqrt((agent1.x-agent2.x)**2 + (agent1.y-agent2.y)**2)

#Randomly position our agents
def baseAgentInit(agent, model):
	dim = model.param('dimension')
	agent.position = [randint(0, dim-1), randint(0, dim-1)]
heli.addHook('baseAgentInit', baseAgentInit)

#Both agents and patches to have x and y properties
baseAgent.x = property(lambda self: self.position[0])
baseAgent.y = property(lambda self: self.position[1])

Agent.patch = property(lambda self: self.model.patches[self.x][self.y])
def moveUp(self): self.position = self.patch.up.position
Agent.moveUp = moveUp
def moveRight(self): self.position = self.patch.right.position
Agent.moveRight = moveRight
def moveDown(self): self.position = self.patch.down.position
Agent.moveDown = moveDown
def moveLeft(self): self.position = self.patch.left.position
Agent.moveLeft = moveLeft
def move(self, x, y):
	dim = model.param('dimension')
	self.position[0] += x
	while self.position[0] > dim-1: self.position[0] -= dim
	self.position[1] += y
	while self.position[1] > dim-1: self.position[1] -= dim
Agent.move = move
def moveTo(self, x, y):
	if x>=self.model.param('dimension') or y>=self.model.param('dimension'): raise IndexError('Dimension is out of range.')
	self.position = [x,y]
Agent.moveTo = moveTo

#Position our patches so we can get them with heli.patches[x][y]
def patchInit(agent, model):
	x=0
	while len(model.patches[x]) >= model.param('dimension'): x+=1
	agent.position = (x, len(model.patches[x]))
	model.patches[x].append(agent)
heli.addHook('patchInit', patchInit)

def modelPreSetup(model):
	model.patches = [[] for i in range(model.param('dimension'))]
	model.param('agents_patch', model.param('dimension')**2)
heli.addHook('modelPreSetup', modelPreSetup)

#Establish grid links
def modelPostSetup(model):
	for patch in model.agents['patch']:
		neighbors = [ patch.up, patch.right, patch.down, patch.left ]
		connections = patch.neighbors #Neighbors that already have a connection
		for n in neighbors:
			if not n in connections:
				patch.newEdge(n, 'space')
		
		# Uncomment the following lines to create half-weighted edges with diagonals
		# 
		# diagonals = [ patch.top.left, patch.right.top, patch.down.right, patch.left.down ]
		# for d in diagonals:
		# 	if not d in connections:
		# 		patch.newEdge(d, 'space', weight=0.5)
heli.addHook('modelPostSetup', modelPostSetup)

#Agent logic
def agentStep(agent, model, stage):
	pass	
heli.addHook('agentStep', agentStep)

#===============
# CONFIGURATION
# Register reporters, plots, and series here
#===============

#===============
# LAUNCH THE GUI
#===============

heli.launchGUI(headless=False)