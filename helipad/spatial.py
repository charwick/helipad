#===============
# Unlike other ABM frameworks like Mesa or Netlogo, Helipad is not specifically designed for spatial models.
# However, it can be extended easily enough to do so using networks to create a grid.
# The functions in this module are in pre-beta and not API stable.
#===============

from random import randint
from math import sqrt, degrees, radians, sin, cos, atan2, pi
import pandas

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

#===============
# THE VISUALIZER
#===============

from helipad.visualize import ChartPlot
import matplotlib.pyplot as plt
class SpatialPlot(ChartPlot):
	type='spatial'
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.agentHistory = {} #For coloring 
		self.params = {
			'patchColormap': 'Blues',
			'patchProperty': 'mapcolor',
			'agentMarker': 'o',
			'agentSize': 5
		}
	
	#Helper function
	def getPatchParamValue(self, patch, t=None):
		if t is not None: return patch.colorData[t]
		elif 'good:' in self.params['patchProperty']: return patch.stocks[self.params['patchProperty'].split(':')[1]]
		else: return getattr(patch, self.params['patchProperty'])
	
	def patchData(self, t=None):
		if not hasattr(self.viz.model, 'patches'): return
		return pandas.DataFrame([[self.getPatchParamValue(p,t) for p in col] for col in self.viz.model.patches])
	
	def agentLoc(self, update=False):
		agents = [a for a in self.viz.model.allagents.values() if a.primitive!='patch']
		if not agents: return
		
		if type(self.params['agentSize']) is int: size = None
		else:
			if 'good:' in self.params['agentSize']: size = [a.stocks[self.params['patchProperty'].split(':')[1]]*10 for a in self.viz.model.allagents.values() if a.primitive!='patch']
			else: size = [getattr(a, self.params['agentSize']) for a in self.viz.model.allagents.values() if a.primitive!='patch']
			#Normalize size here?
		
		#Matplotlib wants the coordinates in two x and y lists to create the plot, but one list of x,y tuples to update it 😡
		if update: return ([(a.x, a.y) for a in agents], [self.viz.model.primitives[a.primitive].breeds[a.breed].color.hex for a in agents], size, [a.id for a in agents])
		else: return ([a.x for a in agents], [a.y for a in agents], [self.viz.model.primitives[a.primitive].breeds[a.breed].color.hex for a in agents], size, [a.id for a in agents])
	
	def launch(self, axes):
		super().launch(axes)
		patchData = self.patchData()
		self.normal = plt.cm.colors.Normalize(patchData.min().min(), patchData.max().max())
		self.patchmap = axes.imshow(patchData, norm=self.normal, cmap=self.params['patchColormap'])
		
		al = self.agentLoc()
		size = al[3] or self.params['agentSize']*10
		self.agentmap = axes.scatter(al[0], al[1], marker=self.params['agentMarker'], c=al[2], s=size)
		self.agentHistory[0] = self.agentLoc(update=True)
		
		#Route clicks
		self.agentmap.set_picker(True)	#Listen for mouse events on nodes
		self.agentmap.set_pickradius(5)	#Set margin of valid events in pixels
		def agentEvent(event):
			agents = [self.viz.model.agent(self.agentHistory[self.viz.scrubval][3][a]) for a in event.ind]
			self.viz.model.doHooks('spatialAgentClick', [agents, self, self.viz.scrubval])
		self.viz.fig.canvas.mpl_connect('pick_event', agentEvent)
		def patchEvent(event):
			if self.axes is not event.inaxes: return
			self.viz.model.doHooks('spatialPatchClick', [self.viz.model.patches[round(event.xdata), round(event.ydata)], self, self.viz.scrubval])
		self.viz.fig.canvas.mpl_connect('button_press_event', patchEvent)
	
	def update(self, data, t):
		pd = self.patchData()
		al = self.agentLoc(update=1)
		self.patchmap.set_data(pd)
		self.agentmap.set_offsets(al[0])
		self.agentmap.set_facecolor(al[1])
		
		#Renormalize color scale
		nmin, nmax = pd.min().min(), pd.max().max()
		self.normal = plt.cm.colors.Normalize(nmin if nmin<self.normal.vmin else self.normal.vmin, nmax if nmax>self.normal.vmax else self.normal.vmax)
		self.patchmap.set_norm(self.normal)
		
		#Store data
		self.agentHistory[t] = al
		for col in self.viz.model.patches:
			for p in col:
				p.colorData[t] = pd[p.x][p.y]
	
	def draw(self, t=None, forceUpdate=False):
		if t is None: t=self.viz.scrubval
		pd = self.patchData(t)
		self.patchmap.set_data(pd)
		self.agentmap.set_offsets(self.agentHistory[t][0])
		self.agentmap.set_facecolor(self.agentHistory[t][1])
		if self.agentHistory[t][2] is not None: self.agentmap.set_sizes(self.agentHistory[t][2])
		super().draw(t, forceUpdate)
	
	def config(self, param, val=None):
		if val is None: return self.params[param]
		else: self.params[param] = val

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
		if type(x) is not int: x,y = x.position
		if x>=self.model.param('x') or y>=self.model.param('y'): raise IndexError('Dimension is out of range.')
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
	
	from helipad.visualize import Charts
	viz = model.useVisual(Charts)
	viz.addPlotType(SpatialPlot)
	mapPlot = viz.addPlot('map', 'Map', type='spatial')
	return mapPlot