"""
Functions and classes to initialize a network of Patch agents and add orientation and motion functions to other agents. This module should not be imported directly; use `model.spatial()` to set up a spatial model instead. See https://helipad.dev/functions/model/spatial/
"""

import warnings
from random import uniform
from math import sqrt, sin, cos, atan2, pi, copysign, floor
from abc import ABC, abstractmethod
from numbers import Number
from helipad.agent import Patch, baseAgent
from helipad.visualize import Charts
from helipad.helpers import ï, Item

#===============
# SETUP
# Create parameters, add functions, and so on
#===============

def spatialSetup(model, dim=10, corners=False, geometry: str='rect', offmap: bool=False, **kwargs):
	"""Set up functions, properties, and methods for a spatial model. https://helipad.dev/functions/model/spatial/"""

	# Backward compatibility
	if 'diag' in kwargs:	#Remove in Helipad 1.7
		corners = kwargs['diag']
		warnings.warn(ï('The `diag` argument is deprecated. Use the `corners` argument instead.'), FutureWarning, 3)

	#Initialize patch container and primitive
	model.agents.addPrimitive('patch', Patch, hidden=True, priority=-10)
	pClasses = {'rect': PatchesRect, 'polar': PatchesPolar, 'geo': PatchesGeo}
	if not isinstance(geometry, str): #We're gonna throw an error anyway if it's not a class or a string
		pClasses[geometry.geometry] = geometry
		geometry = geometry.geometry
	model.patches = pClasses[geometry](dim, corners=corners, offmap=offmap, **kwargs)
	def npsetter(val, item): raise RuntimeError(ï('Patch number cannot be set directly. Set the dim parameter instead.'))
	model.params['num_patch'].getter = lambda item: len(model.patches)
	model.params['num_patch'].setter = npsetter

	#Dimension parameters. Deprecated in Helipad 1.5; remove in Helipad 1.7
	def dimgen(dim, action):
		def dimget(name, model):
			warnings.warn(ï("The {0} parameter is deprecated. Use {1} instead.").format(f"'{dim}'", "model.patches.dim"), FutureWarning, 5)
			return model.patches.dim[0 if dim=='x' else 1]
		def dimset(val, name, model):
			warnings.warn(ï("The {0} parameter is deprecated. Use {1} instead.").format(f"'{dim}'", "model.patches.dim"), FutureWarning, 5)
			model.patches.dim[0 if dim=='x' else 1] = val
		return dimget if action=='get' else dimset
	def wrapget(name, model):
		warnings.warn(ï("The {0} parameter is deprecated. Use {1} instead.").format("'wrap'", "model.patches.wrap"), FutureWarning, 5)
		return model.patches.wrap == (True, True)
	def wrapset(val, name, model):
		warnings.warn(ï("The {0} parameter is deprecated. Use {1} instead.").format("'wrap'", "model.patches.wrap"), FutureWarning, 5)
		model.patches.wrap = val if isinstance(val, (tuple, list)) else (val, val)
	wrap = kwargs['wrap'] if 'wrap' in kwargs else True
	model.params.add('x', ï('Map Width'), 'hidden', dflt=model.patches.dim[0], setter=dimgen('x','set'), getter=dimgen('x','get'))
	model.params.add('y', ï('Map Height'), 'hidden', dflt=model.patches.dim[1], setter=dimgen('y','set'), getter=dimgen('y','get'))
	model.params.add('wrap', ï('Wrap'), 'hidden', dflt=(wrap is True), setter=wrapset, getter=wrapget) #Only checked at the beginning of a model

	#Hook a positioning function or randomly position our agents
	@model.hook(prioritize=True)
	def baseAgentInit(agent, model):
		if agent.primitive == 'patch': return #Patch position is fixed
		p = model.doHooks(['baseAgentPosition', agent.primitive+'Position'], [agent, agent.model])
		if p and len(p) >= 2:
			agent.position = list(p)
			if not offmap and not agent.patch: raise ValueError(ï('Agent is not on a patch.'))
		else:
			while not offmap and not agent.patch:
				agent.position = [uniform(*model.patches.boundaries[0]), uniform(*model.patches.boundaries[1])]

	#MOVEMENT AND POSITION

	#Both agents and patches have x and y properties
	def setx(self, val): self.moveTo(val, self.position[1])
	def sety(self, val): self.moveTo(self.position[0], val)
	baseAgent.x = property(lambda self: self.position[0], setx)
	baseAgent.y = property(lambda self: self.position[1], sety)

	def move(self, x, y):
		mapx, mapy = self.model.patches.dim
		xlim, ylim = self.model.patches.boundaries
		x1 = self.position[0] + x
		y1 = self.position[1] + y

		if self.model.patches.wrap[0]:
			while x1 >= xlim[1]: x1 -= mapx
			while x1 < xlim[0]: x1 += mapx
		else:
			x1 = min(x1, xlim[1])
			x1 = max(x1, xlim[0])

		if self.model.patches.wrap[1]:
			while y1 >= ylim[1]: y1 -= mapy
			while y1 < ylim[0]: y1 += mapy
		else:
			y1 = min(y1, ylim[1])
			y1 = max(y1, ylim[0])

		if (not self.model.patches.offmap and not self.model.patches.at(x1,y1)): warnings.warn(ï('There is no patch at ({0}, {1}).').format(x1, y1), RuntimeWarning, 3)
		else: self.position = [x1, y1]

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
		model.patches.clear()

	#Position our patches in the coordinate system
	@model.hook(prioritize=True)
	def patchInit(agent, model):
		model.patches.place(agent)
		agent.colorData = {}

	#Establish grid links all at once at the end.
	model.hooks.add('modelPostSetup', model.patches.neighbors, True)

	#Don't reset the visualizer if charts is already registered
	if model.visual is None or not isinstance(model.visual, Charts):
		model.useVisual(Charts)

	mapPlot = model.visual.addPlot('map', 'Map', type='agents', layout='spatial', projection=geometry if geometry=='polar' else None)
	return mapPlot

def NotPatches(function):
	"""Wraps a function to execute for all primitives except patches, which are spatially fixed."""
	def np2(self, *args, **kwargs):
		if self.primitive != 'patch': return function(self, *args, **kwargs)
		else: raise RuntimeError(ï('Patches cannot move.'))
	return np2

#===============
# PATCH GEOMETRIES
#===============

class basePatches(list, ABC):
	"""Abstract class defining the methods a coordinate system must implement. https://helipad.dev/functions/basepatches/"""

	@abstractmethod
	def revive(self, coords):
		"""Reinstates a dead patch. https://helipad.dev/functions/basepatches/revive/"""

	@abstractmethod
	def at(self, x, y):
		"""Return the patch at the specified coordinate. https://helipad.dev/functions/basepatches/at/"""

	@abstractmethod
	def neighbors(self, model):
		"""Establishes the spatial network among the patches after initialization. https://helipad.dev/functions/basepatches/neighbors/"""

	@abstractmethod
	def place(self, agent: Patch):
		"""Organize `Patch` objects within the `Patches` object. Takes a `Patch` object when created by `Agents.initialize()`, places it in the appropriate list, and assigns its position property. https://helipad.dev/functions/basepatches/place/"""

	@property
	@abstractmethod
	def boundaries(self):
		"""Maximum and minimum coordinates that agents can take, given the grid dimensions: `((xmin, xmax), (ymin, ymax))` https://helipad.dev/functions/basepatches/#boundaries"""

#Each row and column of equal length
class PatchesRect(basePatches):
	"""Defines a rectangular patch grid. https://helipad.dev/functions/patchesrect/"""
	geometry: str = 'rect'

	#Give patches and agents methods for their neighbors in the four cardinal directions
	def __init__(self, dim, wrap=True, **kwargs):
		if isinstance(wrap, bool): wrap = (wrap, wrap)
		if len(wrap) != 2: raise TypeError(ï('Invalid wrap parameter.'))
		self.wrap = wrap
		if isinstance(dim, int): dim = (dim, dim)
		if len(dim) != 2: raise TypeError(ï('Invalid dimension.'))
		self.dim = dim
		self.offmap = kwargs['offmap']
		self.corners = kwargs['corners']
		if 'noinstall' not in kwargs: RectFuncs.install()
		super().__init__([])

	def at(self, x, y): return self[round(x), round(y)]

	def neighbors(self, model):
		for patch in model.agents['patch']:
			neighbors = [(patch.right, 1), (patch.down, 1)]
			if self.corners: neighbors += [(patch.down.right, self.corners), (patch.left.down, self.corners)]
			for n, weight in neighbors:
				if n: patch.edges.add(n, 'space', weight=weight)

	def place(self, agent: Patch):
		if not super().__len__(): self += [[] for i in range(self.dim[0])]
		x=0
		while len(self[x]) >= self.dim[1]: x+=1		#Find a column that's not full yet
		agent.position = (x, len(self[x]))			#Note the position
		self[x].append(agent)						#Append the agent

	@property
	def boundaries(self): return ((-0.5, self.dim[0]-0.5), (-0.5, self.dim[1]-0.5))

	def __len__(self): return self.dim[0] * self.dim[1]

	def __getitem__(self, key):
		if isinstance(key, int): return super().__getitem__(key)
		else:
			if key[1] is None: return super().__getitem__(key[0])
			if key[0] is None: return [x[key[1]] for x in self]
			patch = super().__getitem__(key[0])[key[1]]
			return patch if not patch.dead else None

	def __setitem__(self, key, val):
		if isinstance(key, int): return super().__setitem__(key, val)
		else: super().__getitem__(key[0])[key[1]] = val

	def __repr__(self): return f'<{self.__class__.__name__}: {self.dim[0]}×{self.dim[1]}>'

	def revive(self, coords):
		super().__getitem__(coords[0])[coords[1]].dead = False

#x,y placement is the same; just need to redefine patch functions and neighbors
class PatchesPolar(PatchesRect):
	"""Defines a polar-coordinate patch grid with θ×r dimensions. `x` is number around, `y` is number out. https://helipad.dev/functions/patchespolar/"""
	geometry: str = 'polar'
	wrap = (True, False) #Wrap around, but not in-to-out.

	def __init__(self, dim, **kwargs):
		PolarFuncs.install()
		super().__init__(dim, noinstall=True, **kwargs)

	def at(self, x, y): return self[floor(x), floor(y)]

	#The usual 3-4 neighbors, but if corners are on, all patches in the center ring will be neighbors
	def neighbors(self, model):
		for patch in model.agents['patch']:
			neighbors = [(patch.clockwise, 1), (patch.inward, 1)]
			if self.corners:
				neighbors += [(patch.clockwise.inward, self.corners), (patch.counterclockwise.inward, self.corners)]
				if patch.y==0:
					pc = neighbors[0][0].clockwise
					while pc.x > patch.x and pc is not patch.counterclockwise:
						neighbors.append((pc, self.corners))
						pc = pc.clockwise

			for n, weight in neighbors:
				if n: patch.edges.add(n, 'space', weight=weight)

	@property #((xmin, xmax),(ymin, ymax))
	def boundaries(self): return ((0, self.dim[0]), (0, self.dim[1]))

class PatchesGeo(basePatches):
	"""Defines a set of patches with arbitrary polygonal shapes. https://helipad.dev/functions/patchesgeo/"""
	geometry: str = 'geo'
	def __init__(self, dim=None, wrap=True, corners=True, **kwargs):
		import shapely
		self.shapely = shapely
		self.shapes = []
		self.corners = corners
		if isinstance(wrap, bool): wrap = (wrap, wrap)
		if len(wrap) != 2: raise TypeError(ï('Invalid wrap parameter.'))
		self.wrap = wrap
		self.offmap = kwargs['offmap']

		def vertices(patch): return patch.polygon.exterior.xy
		def area(patch): return patch.polygon.area
		def center(patch): return (patch.polygon.centroid.x, patch.polygon.centroid.y) if hasattr(patch, 'polygon') else None
		def agentsOn(patch):
			agents = []
			for a in patch.model.agents.all:
				if a.primitive == 'patch': continue
				if patch.polygon.covers(self.shapely.Point(*a.position)): agents.append(a)
			return agents
		for prop in [vertices, area, center, agentsOn]: setattr(Patch, prop.__name__, property(prop))
		Patch.position = property(center)
		RectFuncs.install(patches=False)

	def __getitem__(self, val):
		if isinstance(val, str): patch = [p for p in self if p.name==val][0]
		else: patch = super().__getitem__(val)
		return patch if not patch.dead else None

	def __len__(self): return len(self.shapes)

	@property
	def names(self):
		return [p.name for p in self if p.name is not None]

	@property
	def boundaries(self):
		bounds = [s.shape.bounds for s in self.shapes]
		minx, miny, maxx, maxy = bounds[0] if bounds else (0,0,0,0)
		for b in bounds:
			minx, maxx = min(minx, b[0]), max(maxx, b[2])
			miny, maxy = min(miny, b[1]), max(maxy, b[3])
		return ((minx, maxx), (miny, maxy))

	@property
	def dim(self):
		bounds = self.boundaries
		return (bounds[0][1]-bounds[0][0], bounds[1][1]-bounds[1][0])

	def add(self, shape, name=None):
		"""Add a polygonal patch to the map. https://helipad.dev/functions/patchesgeo/add/"""
		if isinstance(shape, list): shape = self.shapely.Polygon(shape)
		elif isinstance(shape, self.shapely.MultiPolygon):
			warnings.warn(ï('MultiPolygons are not supported as patches. Taking the first polygon…'), RuntimeWarning, 2)
			shape = shape.geoms[0]
		if name and name in self.names: raise KeyError(ï('Patch with name \'{0}\' already exists.').format(name))
		item = Item(shape=shape, name=name, borders=[], corners=[]) #Have to store this as a wrapper item because Shapely objects are immutable

		#Ensure no overlap and calculate neighbors
		for i,p in enumerate(self.shapes):
			intersection = shape.intersection(p.shape)
			if not intersection.is_empty:
				if isinstance(intersection, (self.shapely.LineString, self.shapely.MultiLineString)): item.borders.append(p)
				elif isinstance(intersection, self.shapely.Point): item.corners.append(p)
				else:
					pn = f'\'{p.name}\'' if p.name else i
					raise ValueError(ï('Polygon {0} overlaps existing patch {1}.').format(name, pn))

		self.shapes.append(item)

	def at(self, x, y):
		pt = self.shapely.Point(x,y)
		for p in self:
			if p.polygon.covers(pt): return p if not p.dead else None

	def neighbors(self, model):
		for p in self.shapes:
			for e in p.borders: p.patch.edges.add(e.patch, 'space')
			if self.corners:
				for e in p.corners: p.patch.edges.add(e.patch, 'space', weight=self.corners)

	def place(self, agent: Patch):
		shape = self.shapes[super().__len__()]
		agent.polygon, agent.name = shape.shape, shape.name
		shape.patch = agent
		self.append(agent)

	def revive(self, index):
		if isinstance(index, str): [p for p in self if p.name==index][0].dead = False
		else: super().__getitem__(index).dead = False

#===============
# COORDINATE SYSTEMS
#===============

class RectFuncs:
	"""Installs distance, neighbor, and angle functions for rectangular coordinates into agent objects. This is a static class and should not be instantiated."""
	@staticmethod
	def install(patches=True, agents=True, allagents=True):
		if patches:
			for p in ['up', 'right', 'down', 'left', 'agentsOn', 'center', 'area', 'vertices']:
				setattr(Patch, p, property(getattr(RectFuncs,p)))
		if agents:
			for f in ['moveUp', 'moveRight', 'moveDown', 'moveLeft', 'forward', 'orientTo']:
				setattr(baseAgent, f, NotPatches(getattr(RectFuncs,f)))
		if allagents:
			for h in ['_offset', 'distanceFrom']:
				setattr(baseAgent, h, getattr(RectFuncs,h))

	def up(patch):
		if patch.y==0 and not patch.model.patches.wrap[1]: return None
		return patch.model.patches[patch.x, patch.y-1 if patch.y > 0 else patch.model.patches.dim[1]-1]

	def right(patch):
		if patch.x>=patch.model.patches.dim[0]-1 and not patch.model.patches.wrap[0]: return None
		return patch.model.patches[patch.x+1 if patch.x < patch.model.patches.dim[0]-1 else 0, patch.y]

	def down(patch):
		if patch.y>=patch.model.patches.dim[1]-1 and not patch.model.patches.wrap[1]: return None
		return patch.model.patches[patch.x, patch.y+1 if patch.y < patch.model.patches.dim[1]-1 else 0]

	def left(patch):
		if patch.x==0 and not patch.model.patches.wrap[0]: return None
		return patch.model.patches[patch.x-1 if patch.x > 0 else patch.model.patches.dim[0]-1, patch.y]

	def agentsOn(patch):
		for prim, lst in patch.model.agents.items():
			if prim=='patch': continue
			yield from [a for a in lst if patch.x-0.5<=a.x<patch.x+0.5 and patch.y-0.5<=a.y<patch.y+0.5]

	def center(patch): return patch.position
	def area(patch): return 1
	def vertices(patch):
		pp = patch.position
		return ((pp[0]-0.5, pp[1]-0.5), (pp[0]-0.5, pp[1]+0.5), (pp[0]+0.5, pp[1]+0.5), (pp[0]+0.5, pp[1]-0.5))

	def moveUp(agent): agent.move(0, -1)
	def moveRight(agent): agent.move(1, 0)
	def moveDown(agent): agent.move(0, 1)
	def moveLeft(agent): agent.move(-1, 0)
	def forward(self, steps=1):
		"""Move forward `steps` steps in the direction of `agent.orientation`."""
		self.move(steps * cos(self.rads-pi/2), steps * sin(self.rads-pi/2))

	def orientTo(agent, x, y=None):
		if not isinstance(x, Number): x,y = x.position
		difx, dify = agent._offset(x, y)
		agent.rads = atan2(dify,difx) + 0.5*pi #atan calculates 0º pointing East. We want 0º pointing North

	#Internal function  to calculate x,y distances s.t. wrap constraints for distance and orientation purposes
	def _offset(agent, x, y):
		difx, dify = x - agent.x, y - agent.y
		if agent.model.patches.wrap[0]:
			crossx = difx - copysign(agent.model.patches.dim[0], difx)
			if abs(crossx) < abs(difx): difx = crossx
		if agent.model.patches.wrap[1]:
			crossy = dify - copysign(agent.model.patches.dim[1], dify)
			if abs(crossy) < abs(dify): dify = crossy
		return (difx, dify)

	def distanceFrom(agent, agent2):
		difx, dify = agent._offset(agent2.x, agent2.y)
		return sqrt(difx**2 + dify**2)

class PolarFuncs:
	"""Installs distance, neighbor, and angle functions for polar coordinates into agent objects. This is a static class and should not be instantiated."""
	@staticmethod
	def install(patches=True, agents=True, allagents=True):
		if patches:
			for p in ['inward', 'outward', 'clockwise', 'counterclockwise', 'agentsOn', 'center', 'area', 'vertices']:
				setattr(Patch, p, property(getattr(PolarFuncs,p)))
		if agents:
			for f in ['moveInward', 'moveOutward', 'moveClockwise', 'moveCounterclockwise', 'forward', 'orientTo']:
				setattr(baseAgent, f, NotPatches(getattr(PolarFuncs,f)))
		if allagents:
			baseAgent.distanceFrom = PolarFuncs.distanceFrom

	def inward(patch):
		if patch.y==0: return None
		return patch.model.patches[patch.x, patch.y-1]

	def outward(patch):
		if patch.y>=patch.model.patches.dim[1]-1: return None
		return patch.model.patches[patch.x, patch.y+1]

	def clockwise(patch):
		return patch.model.patches[patch.x+1 if patch.x < patch.model.patches.dim[0]-1 else 0, patch.y]

	def counterclockwise(patch):
		return patch.model.patches[patch.x-1 if patch.x > 0 else patch.model.patches.dim[0]-1, patch.y]

	def agentsOn(patch):
		for prim, lst in patch.model.agents.items():
			if prim=='patch': continue
			yield from [a for a in lst if floor(a.x)==patch.x and floor(a.y)==patch.y]

	def center(patch): return (patch.position[0]+0.5, patch.position[1]+0.5)
	def area(patch): return (1/patch.model.patches.dim[0])*pi*((patch.position[1]+1)**2-patch.position[1]**2)
	def vertices(patch):
		pp = patch.position
		return (pp, (pp[0], pp[1]+1), (pp[0]+1, pp[1]+1), (pp[0]+1, pp[1]))

	def moveInward(agent): agent.move(0, -1)
	def moveOutward(agent): agent.move(0, 1)
	def moveClockwise(agent): agent.move(1, 0)
	def moveCounterclockwise(agent): agent.move(-1, 0)
	def forward(agent, steps=1):
		"""Move forward `steps` steps in the direction of `agent.orientation`."""
		#2π-self.rads to make it go clockwise
		th1 = 2*pi-(2*pi/agent.model.patches.dim[0] * agent.x)
		newth = th1 + atan2(steps*sin(2*pi-agent.rads-th1), agent.y+steps*cos(2*pi-agent.rads-th1))
		newx = (2*pi-newth)/(2*pi/agent.model.patches.dim[0])
		if newx > agent.model.patches.dim[0]: newx -= agent.model.patches.dim[0]
		newr = sqrt(agent.y**2 + steps**2 + 2*agent.y*steps*cos(2*pi-agent.rads-th1))
		agent.move(newx-agent.x, newr-agent.y)

	def orientTo(agent, x, y=None):
		if not isinstance(x, Number): x,y = x.position
		th1 = 2*pi-(2*pi/agent.model.patches.dim[0] * agent.x)
		th2 = 2*pi-(2*pi/agent.model.patches.dim[0] * x)
		agent.rads = pi - atan2(agent.y * sin(th1) - y * sin(th2), agent.y * cos(th1) - y * cos(th2))

	def distanceFrom(agent, agent2):
		th1 = agent.x * 2*pi /agent.model.patches.dim[0]
		th2 = agent2.x * 2*pi /agent.model.patches.dim[0]
		return sqrt(agent.y**2 + agent2.y**2 - 2*agent.y*agent2.y*cos(th1-th2))