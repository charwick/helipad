# An implementation of Conway's Game Of Life
# https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life

from helipad import Helipad
from random import getrandbits

heli = Helipad()
heli.name = 'Game of Life'
heli.stages = 2
heli.param('refresh', 1)

heli.agents.removePrimitive('agent')
mapPlot = heli.spatial(dim=30, wrap=True, corners=True)
mapPlot.config('patchProperty', 'active')

def setdim(model, var, val): model.patches.dim = (int(val), int(val))
heli.params.add('dim', 'Dimension', 'slider', 30, opts={'low': 4, 'high': 30, 'step': 1}, runtime=False, callback=setdim)

@heli.hook
def patchInit(patch, model):
	patch.active = False

@heli.hook
def patchStep(patch, model, stage):
	if stage==1: #Calculate neighbors *before* dying or coming to life
		patch.activeNeighbors = len([n for n in patch.neighbors if n.active])
	elif stage==2:
		if patch.active and not 1 < patch.activeNeighbors < 4: patch.active = False
		elif not patch.active and patch.activeNeighbors == 3: patch.active = True

#Pause on launch to allow the user to toggle patches
@heli.hook
def modelStep(model, stage):
	if model.t==1 and stage==1: model.stop()

@heli.hook
def patchClick(patch, plot, t):
	patch.active = not patch.active
	plot.update(None, t)
	plot.draw(t, forceUpdate=True)

@heli.button
def Randomize(model):
	if not model.hasModel: return
	for p in model.agents['patch']:
		p.active = bool(getrandbits(1))
	if model.visual:
		model.visual['map'].update(None, model.t)
		model.visual['map'].draw(model.t, forceUpdate=True)

heli.launchCpanel()