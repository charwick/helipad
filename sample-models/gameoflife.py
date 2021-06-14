# An implementation of Conway's Game Of Life
# https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life

from helipad import Helipad

heli = Helipad()
heli.name = 'Game of Life'
heli.stages = 2
heli.param('refresh', 1)

heli.removePrimitive('agent')
mapPlot = heli.spatial(x=30, square=True, wrap=True, diag=True)
mapPlot.config('patchProperty', 'active')

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

heli.launchCpanel()