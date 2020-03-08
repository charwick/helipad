# Unlike other ABM frameworks like Mesa or Netlogo, Helipad is not specifically designed for spatial models.
# However, it can be extended easily enough to do so using networks to create a grid.

#===============
# SETUP
# Instantiate the object and add parameters, breeds, and goods below.
#===============

from model import Helipad
from agent import baseAgent, Agent
from random import randint

heli = Helipad()
heli.order = 'random'
heli.dimension = 5 #Not a standard setup property, but we can store it here to use later

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
		return self.model.patches[self.x][self.y-1 if self.y > 0 else self.model.dimension-1]
	
	@property
	def right(self):
		return self.model.patches[self.x+1 if self.x < self.model.dimension-1 else 0][self.y]
	
	@property
	def down(self):
		return self.model.patches[self.x][self.y+1 if self.y < self.model.dimension-1 else 0]
	
	@property
	def left(self):
		return self.model.patches[self.x-1 if self.x > 0 else self.model.dimension-1][self.y]
	
	@property
	def agentsOn(self):
		agents = []
		for a in self.model.agents['agent']:
			if a.x==self.x and a.y==self.y:
				agents.append(a)
		return agents
	
heli.addPrimitive('patch', Patch, dflt=heli.dimension**2, low=0, high=100)


#===============
# BEHAVIOR
#===============

#Randomly position our agents
def baseAgentInit(agent, model):
	agent.position = [randint(0, model.dimension-1), randint(0, model.dimension-1)]
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
	self.position[0] += x
	while self.position[0] > self.model.dimension-1: self.position[0] -= self.model.dimension
	self.position[1] += y
	while self.position[1] > self.model.dimension-1: self.position[1] -= self.model.dimension
Agent.move = move
def moveTo(self, x, y):
	if x>=self.model.dimension or y>=self.model.dimension: raise IndexError('Dimension is out of range.')
	self.position = [x,y]
Agent.moveTo = moveTo

#Position our patches so we can get them with heli.patches[x][y]
def patchInit(agent, model):
	x=0
	while len(model.patches[x]) >= model.dimension: x+=1
	agent.position = (x, len(model.patches[x]))
	model.patches[x].append(agent)
heli.addHook('patchInit', patchInit)

def modelPreSetup(model):
	model.patches = [[] for i in range(model.dimension)]
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