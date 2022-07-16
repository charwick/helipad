# ==========
# The matplotlib interface for plotting
# Do not run this file; import model.py and run from your file.
# ==========

import sys
from abc import ABC, abstractmethod
from math import sqrt, ceil
from numpy import ndarray, asanyarray, log10
import matplotlib, matplotlib.pyplot as plt, matplotlib.style as mlpstyle
from helipad.helpers import *
mlpstyle.use('fast')

#======================
# TOP-LEVEL VISUALIZERS
# These two use Matplotlib, but subclasses of BaseVisualization don't necessarily have to.
#======================

#Used for creating an entirely new visualization window.
class BaseVisualization(ABC):
	isNull = True

	#Create the window. Mandatory to implement
	@abstractmethod
	def launch(self, title): pass

	#Refresh every so many periods. Mandatory to implement
	#data is the *incremental* data
	@abstractmethod
	def update(self, data): pass

	#Do something when events happen. Mandatory to implement.
	@abstractmethod
	def event(self, t, color, **kwargs): pass

	#Called from model.terminate(). Optional to implement
	def terminate(self, model): pass

class MPLVisualization(BaseVisualization):
	keys = {}

	def __init__(self, model):
		self.model = model #Unhappy with this
		self.plots = {}
		self.selector = model.params.add('plots', _('Plots'), 'checkgrid', [], opts={}, runtime=False, config=True)
		self.dim = None
		self.pos = (400, 0)

		def pause(model, event):
			if model.hasModel and event.canvas is self.fig.canvas:
				if model.running: model.stop()
				else: model.start()
		self.addKeypress(' ', pause)

		if isNotebook():
			from IPython import get_ipython
			get_ipython().magic('matplotlib widget')
		else: matplotlib.use('TkAgg') #macosx would be preferable (Retina support), but it blocks the cpanel while running

	#Subclasses should call super().launch **after** the figure is created.
	@abstractmethod
	def launch(self, title, dim=None, pos=None):
		if not isNotebook():
			self.fig.canvas.manager.set_window_title(title)
			if self.model.cpanel: self.model.cpanel.setAppIcon()
		self.fig.tight_layout()
		self.fig.canvas.mpl_connect('close_event', self.model.terminate)
		self.fig.canvas.mpl_connect('key_press_event', self.sendEvent)
		self.fig.canvas.mpl_connect('pick_event', self.sendEvent)
		self.fig.canvas.mpl_connect('button_press_event', self.sendEvent)
		self.lastUpdate = 0

		#Resize and position graph window if applicable
		fm = self.fig.canvas.manager
		if hasattr(fm, 'window'):
			if not self.dim:
				#This should be the window height, but MPL only allows us to set the figure height.
				#MacOS doesn't let us create a window taller than the screen, but we have to account for
				#the height of the window frame crudely in Windows.
				height = fm.window.winfo_screenheight()
				if sys.platform=='win32': height -= 150

				width = fm.window.winfo_screenwidth()*2/3
				width = min(width, fm.window.winfo_screenwidth()-400)
			else: width, height = self.dim

			self.fig.set_size_inches(width/self.fig.dpi, height/self.fig.dpi)
			fm.window.wm_geometry(f'+{self.pos[0]}+{self.pos[1]}')

	def sendEvent(self, event):
		axes = event.artist.axes if hasattr(event, 'artist') else event.inaxes
		if axes is not None:
			for p in self.activePlots.values():
				if axes is p.axes:
					p.MPLEvent(event)
					break

		if event.name=='key_press_event' and event.key in self.keys:
			for f in self.keys[event.key]: f(self.model, event)

	def addKeypress(self, key, fn):
		if not key in self.keys: self.keys[key] = []
		self.keys[key].append(fn)

	@property
	def activePlots(self):
		return {k:plot for k,plot in self.plots.items() if plot.selected}

	@property
	def isNull(self):
		return not [plot for plot in self.plots.values() if plot.selected]

class TimeSeries(MPLVisualization):
	def __init__(self, model):
		super().__init__(model)
		self.verticals = []

		#Plot categories
		self.addPlot('utility', 'Utility', selected=False)

		if len(model.goods) >= 2: self.addPlot('demand', _('Demand'), selected=False)
		if model.goods.money is not None: self.addPlot('money', _('Money'), selected=False)

		#Toggle legend boxes all at once
		#Use event.canvas.figure and not self.fig so it pertains to the current window
		def toggle(model, event):
			for axes in event.canvas.figure.axes:
				leg = axes.get_legend()
				leg.set_visible(not leg.get_visible())
			event.canvas.draw_idle()
		self.addKeypress('t', toggle)

		#Delete the corresponding series when a reporter is removed
		@model.hook('removeReporter')
		def deleteSeries(data, key):
			for p in self.plots.values():
				for s in p.series:
					if s.reporter==key:
						# Remove subseries
						for ss in s.subseries:
							for sss in self.model.plots[s.plot].series:
								if sss.reporter == ss:
									self.plots[s.plot].series.remove(sss)
									continue
						self.plots[s.plot].series.remove(s)

		#Move the plots parameter to the end when the cpanel launches
		@model.hook('CpanelPreLaunch')
		def movePlotParam(model):
			model.params['plots'] = model.params.pop('plots')

	#listOfPlots is the trimmed model.plots list
	def launch(self, title):
		if not self.activePlots: return #Windowless mode

		self.resolution = 1
		if isNotebook():
			plt.close() #Clean up after any previous runs
			matplotlib.rcParams['figure.figsize'] = [9, 7]

		#fig is the figure, plots is a list of AxesSubplot objects
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(self.activePlots), sharex=True, num=title if isNotebook() else None)
		super().launch(title)

		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activePlots.values(), plots): plot.launch(axes)

		#Style plots
		self.fig.subplots_adjust(hspace=0, bottom=0.05, right=1, top=0.97, left=0.1)
		# plt.setp([a.get_xticklabels() for a in self.fig.axes[:-1]], visible=False)	#What was this for again…?

		self.fig.canvas.draw_idle()
		plt.show(block=False)

	def terminate(self, model):
		if self.isNull:
			model.params['csv'].enable()
			if not isinstance(model.param('stopafter'), str): model.params['stopafter'].enable()

	def update(self, data):
		newlen = len(next(data[x] for x in data))
		if self.resolution > 1: data = {k: keepEvery(v, self.resolution) for k,v in data.items()}
		time = newlen + len(next(iter(self.activePlots.values())).series[0].fdata)*self.resolution
		for plot in self.activePlots.values(): plot.update(data, time) #Append new data to series

		#Redo resolution at 2500, 25000, etc
		if 10**(log10(time/2.5)-3) >= self.resolution:
			self.resolution *= 10
			for plot in self.activePlots.values():
				for serie in plot.series:
					serie.fdata = keepEvery(serie.fdata, 10)
			if self.resolution > self.model.param('refresh'): self.model.param('refresh', self.resolution)

		for plot in self.activePlots.values(): plot.draw(time) #Update the actual plots. Has to be after the new resolution is set
		if self.fig.stale: self.fig.canvas.draw_idle()
		self.fig.canvas.flush_events() #Listen for user input

	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, selected=True, logscale=False, stack=False):
		plot = TimeSeriesPlot(viz=self, name=name, label=label, logscale=logscale, stack=stack)

		self.selector.addItem(name, label, position, selected)
		if position is None or position > len(self.plots): self.plots[name] = plot
		else:		#Reconstruct the dicts because there's no insert method…
			newplots, i = ({}, 1)
			for k,v in self.plots.items():
				if position==i:
					newplots[name] = plot
				newplots[k] = v
				i+=1
			self.plots = newplots

		plot.selected = selected #Do this after CheckgridParam.addItem
		return plot

	def removePlot(self, name, reassign=None):
		if self.model.cpanel: raise RuntimeError(_('Cannot remove plots after control panel is drawn.'))
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return

		if not name in self.plots:
			warnings.warn(_('No plot \'{}\' to remove.').format(name), None, 2)
			return False

		if reassign is not None: self.plots[reassign].series += self.plots[name].series
		del self.plots[name]
		del self.selector.opts[name]
		del self.selector.vars[name]
		if name in self.selector.default: self.selector.default.remove(name)
		return True

	def event(self, t, color='#CC0000', linestyle='--', linewidth=1, **kwargs):
		if not hasattr(self, 'fig'): return
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.activePlots.values()])

		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.plots.values())).axes.text(t, 0, label, horizontalalignment='center')

class Charts(MPLVisualization):
	def __init__(self, model):
		super().__init__(model)
		self.events = {}
		self.plotTypes = {}

		for p in [BarChart, NetworkPlot, TimeSeriesPlot]: self.addPlotType(p)
		model.params['refresh'].runtime=False
		self.refresh = model.params['refresh']
		self.model = model # :(

	def launch(self, title):
		if not self.activePlots: return #Windowless mode
		from matplotlib.widgets import Slider

		n = len(self.activePlots)
		x = ceil(sqrt(n))
		y = ceil(n/x)
		if isNotebook():
			plt.close() #Clean up after any previous runs
			matplotlib.rcParams['figure.figsize'] = [9, 7]

		#Add the subplots individually rather than using plt.subplots() so we can mix and match projections
		self.fig = plt.figure()
		plots = list(self.activePlots.values())
		for i in range(n):
			plots[i].launch(self.fig.add_subplot(y,x,i+1, projection=plots[i].projection))
		super().launch(title)

		#Time slider
		ref = self.refresh.get()
		self.fig.subplots_adjust(bottom=0.12) #Make room for the slider
		sax = self.fig.add_axes([0.1,0.01,.75,0.03], facecolor='#EEF')
		self.timeslider = Slider(sax, 't=', 0, ref, ref, valstep=ref, closedmin=False)
		self.timeslider.on_changed(self.scrub)

		self.fig.canvas.draw_idle()
		plt.show(block=False)

	def update(self, data):
		data = {k:v[-1] for k,v in data.items()}
		t = self.model.t #cheating?
		for c in self.activePlots.values(): c.update(data, t)

		#Update slider. This calls self.scrub(), which in turn calls chart.draw()
		self.timeslider.valmax = t
		self.timeslider.set_val(t)
		self.timeslider.ax.set_xlim(0,t) #Refresh

		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')
		if self.fig.stale: self.fig.canvas.draw_idle()
		self.fig.canvas.flush_events() #Listen for user input

	#Update the graph to a particular model time
	def scrub(self, t):
		self.scrubval = t
		for c in self.activePlots.values(): c.draw(t)
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')

	def addPlot(self, name, label, type=None, selected=True, **kwargs):
		self.selector.addItem(name, label, selected)
		self.type = type if type is not None else 'bar'
		if self.type not in self.plotTypes: raise KeyError(_('\'{}\' is not a registered plot visualizer.').format(self.type))
		self.plots[name] = self.plotTypes[self.type](name=name, label=label, viz=self, selected=True, **kwargs)
		return self.plots[name]

	def addPlotType(self, clss):
		if not issubclass(clss, ChartPlot): raise TypeError(_('New plot types must subclass ChartPlot.'))
		self.plotTypes[clss.type] = clss

	def removePlot(self, name):
		if self.model.cpanel: raise RuntimeError(_('Cannot remove plots after control panel is drawn.'))
		if isinstance(name, list):
			for p in name: self.removePlot(p)
			return

		if not name in self.plots:
			warnings.warn(_('No plot \'{}\' to remove.').format(name), None, 2)
			return False

		del self.plots[name]
		return True

	def event(self, t, color='#FDC', **kwargs):
		ref = self.refresh.get()
		self.events[ceil(t/ref)*ref] = color

#======================
# PLOT-LEVEL VISUALIZERS
# Plug into either TimeSeries or Charts as one of the subplots
#======================

#Used for creating a synchronic plot area in the Charts visualizer. Must interface with Matplotlib and specify class.type.
#Extra kwargs in Charts.addPlot() are passed to ChartPlot.__init__().
class ChartPlot(Item):
	def __init__(self, **kwargs):
		if 'projection' not in kwargs and not hasattr(self, 'projection'): self.projection = None
		super().__init__(**kwargs)

	@property
	def selected(self): return self.viz.model.params['plots'].get(self.name)

	@selected.setter
	def selected(self, val): self.active(val)

	def active(self, val, updateGUI=True):
		self.viz.model.params['plots'].set(self.name, bool(val))
		if updateGUI and not isNotebook() and hasattr(self, 'check'):
			self.check.set(val)

	#Receives an AxesSubplot object used for setting up the plot area. super().launch(axes) should be called from the subclass.
	@abstractmethod
	def launch(self, axes):
		self.axes = axes
		axes.set_title(self.label, fontdict={'fontsize':10})

	#Receives a 1-dimensional dict with only the most recent value of each column
	#The subclass is responsible for storing the relevant data internally
	@abstractmethod
	def update(self, data, t): pass

	#Receives the time to scrub to
	@abstractmethod
	def draw(self, t, forceUpdate=False):
		if forceUpdate: self.viz.fig.canvas.draw_idle()

	def remove(self):
		self.viz.removePlot(self.name)

	#Override in order to catch plot-specific keypresses, clicks, or picks
	def MPLEvent(self, event): pass

class TimeSeriesPlot(ChartPlot):
	type = 'timeseries'
	def __init__(self, **kwargs):
		self.series = []
		self.scrubline = None
		for p in ['logscale', 'stack']:
			if p not in kwargs: kwargs[p] = False
		super().__init__(**kwargs)

	#First arg is a reporter name registered in DataCollector, or a lambda function
	#Second arg is the series name. Use '' to not show in the legend.
	#Third arg is the plot's hex color, or a Color object
	def addSeries(self, reporter, label, color, style='-', visible=True):
		if not isinstance(color, Color): color = Color(color)

		#Check against columns and not reporters so subseries work
		if not callable(reporter) and not reporter in self.viz.model.data.columns:
			raise KeyError(_('Reporter \'{}\' does not exist. Be sure to register reporters before adding series.').format(reporter))

		#Add subsidiary series (e.g. percentile bars)
		subseries = []
		if reporter in self.viz.model.data.reporters and self.viz.model.data.reporters[reporter].children:
			for p in self.viz.model.data.reporters[reporter].children:
				if '-unsmooth' in p: continue #Don't plot the unsmoothed series
				subseries.append(self.addSeries(p, '', color.lighten(), style='--'))

		#Since many series are added at setup time, we have to de-dupe
		for s in self.series:
			if s.reporter == reporter:
				self.series.remove(s)

		series = Series(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=self.name, visible=visible)
		self.series.append(series)
		return series

	def launch(self, axes):
		self.axes = axes
		axes.margins(x=0)
		if self.stack:
			lines = axes.stackplot([], *[[] for s in self.series], color=[s.color.hex for s in self.series])
			for series, poly in zip(self.series, lines): series.poly = poly
			axes.margins(y=0)

		if self.logscale:
			axes.set_yscale('log')
			axes.set_ylim(1/2, 2, auto=True)

		#Create a line for each series
		#Do this even for stackplots because the line object is necessary to create the legend
		for series in self.series:
			series.line, = axes.plot([], label=series.label, color=series.color.hex, linestyle=series.style)
			series.fdata = []

		#Set up the legend for click events on both the line and the legend
		leg = axes.legend(loc='upper right')
		for legline, label in zip(leg.get_lines(), leg.get_texts()):
			legline.set_picker(True)	#Listen for mouse events on the legend line
			legline.set_pickradius(5)	#Set margin of valid events in pixels
			label.set_picker(5)			#Do both on the legend text
			for s in self.series:
				if s.label==label.get_text():
					s.legline = legline
					s.legtext = label
					label.axes = axes #Necessary because an MPL bug fails to set the axes property of the text labels. Fixed in 3.5.0 (#20458)
					break

		for series in self.series: #Make sure we start out with the user-set visibility
			if series.label and not series._visible: series.visible = False

	def update(self, data, t):
		firstdata = next(iter(data.values()))
		if isinstance(firstdata, list): newlen, res = len(firstdata), self.resolution
		else:
			newlen = 1
			res = self.viz.model.param('refresh')
			data = {k: [v] for k,v in data.items()}
		for serie in self.series:
			if callable(serie.reporter):						#Lambda functions
				for i in range(newlen):
					serie.fdata.append(serie.reporter(t-(newlen-1-i)*res))
			elif serie.reporter in data: serie.fdata += data[serie.reporter] #Actual data
			else: continue									#No data

	def draw(self, t, forceUpdate=False):
		if self.scrubline is not None:
			self.scrubline.remove()
			self.scrubline = None

		#Draw new data if this is a new refresh
		if t==len(self.series[0].fdata)*self.resolution:
			tseries = range(0, t, self.resolution)

			#No way to update the stack (?) so redraw it from scratch
			if self.stack:
				lines = self.axes.stackplot(tseries, *[s.fdata for s in self.series], colors=[s.color.hex for s in self.series])
				for series, poly in zip(self.series, lines): series.poly = poly
			else:
				for serie in self.series:
					serie.line.set_ydata(serie.fdata)
					serie.line.set_xdata(tseries)
				self.axes.relim()
				self.axes.autoscale_view(tight=False)

			#Prevent decaying averages on logscale graphs from compressing the entire view
			ylim = self.axes.get_ylim()
			if self.axes.get_yscale() == 'log' and ylim[0] < 10**-6: self.axes.set_ylim(bottom=10**-6)
			super().draw(t, forceUpdate)

		#Note the position in the old data if we're scrubbing
		else:
			self.scrubline = self.axes.axvline(x=t, color='#330000')

	def MPLEvent(self, event):
		#Toggle legend boxes one at a time if we're in the Charts visualizer
		if hasattr(self.viz, 'scrub') and event.name=='key_press_event' and event.key=='t':
			leg = self.axes.get_legend()
			leg.set_visible(not leg.get_visible())
			event.canvas.draw_idle()

		#Toggle lines on and off when clicking the legend
		if event.name=='pick_event':
			c1 = event.artist					#The label or line that was clicked
			for s in self.series:
				if s.label and (c1 is s.legline or c1 is s.legtext):
					s.toggle()
					break

	@property
	def resolution(self):
		return self.viz.resolution if hasattr(self.viz, 'resolution') else int(self.viz.model.param('refresh'))

class BarChart(ChartPlot):
	type = 'bar'
	def __init__(self, **kwargs):
		for arg in ['horizontal', 'logscale']:
			if not arg in kwargs: kwargs[arg] = False
		super().__init__(**kwargs)
		self.bars = []

	def addBar(self, reporter, label, color='blue', position=None):
		if not isinstance(color, Color): color = Color(color)
		bar = Item(reporter=reporter, label=label, color=color)

		#Add subsidiary series (e.g. percentile bars)
		bar.err = []
		if reporter in self.viz.model.data.reporters and self.viz.model.data.reporters[reporter].children:
			for p in self.viz.model.data.reporters[reporter].children:
				if '-unsmooth' in p: continue
				bar.err.append(p)

		if position is None or position>=len(self.bars): self.bars.append(bar)
		else: self.bars.insert(position-1, bar)

	def launch(self, axes):
		super().launch(axes)
		axes.spines['top'].set_visible(False)
		axes.spines['right'].set_visible(False)

		cfunc, eax = (axes.barh, 'xerr') if self.horizontal else (axes.bar, 'yerr')
		kwa = {eax: [0 for bar in self.bars]} #Make sure our error bars go the right way
		rects = cfunc(range(len(self.bars)), [0 for i in self.bars], color=[bar.color.hex for bar in self.bars], **kwa)
		errors = rects.errorbar.lines[2][0].properties()['paths'] #Hope MPL's API doesn't ever move this…!
		for bar, rect, err in zip(self.bars, rects, errors):
			bar.element = rect
			bar.errPath = err.vertices
			bar.errHist = []
			bar.data = []

		cstlfunc, cstfunc = (axes.set_yticklabels, axes.set_yticks) if self.horizontal else (axes.set_xticklabels, axes.set_xticks)
		cstfunc(range(len(self.bars)))
		cstlfunc([bar.label for bar in self.bars])
		axes.margins(x=0)

		if self.logscale:
			if self.horizontal:
				axes.set_xscale('log')
				axes.set_xlim(1/2, 2, auto=True)
			else:
				axes.set_yscale('log')
				axes.set_ylim(1/2, 2, auto=True)

	def update(self, data, t):
		getlim, setlim = (self.axes.get_xlim, self.axes.set_xlim) if self.horizontal else (self.axes.get_ylim, self.axes.set_ylim)
		lims = list(getlim())
		for b in self.bars:
			b.data.append(data[b.reporter])
			if data[b.reporter] < lims[0]: lims[0] = data[b.reporter]
			if data[b.reporter] > lims[1]: lims[1] = data[b.reporter]

			if b.err:
				errs = [data[e] for e in b.err]
				errs.sort()
				for i,cap in enumerate(b.errPath): #Should only be 2 of these, but errs could be any length
					if errs[i] < lims[0]: lims[0] = errs[i]
					if errs[i] > lims[1]: lims[1] = errs[i]
				b.errHist.append(errs)

		setlim(lims)
		self.axes.autoscale_view(tight=False)

	def draw(self, t=None, forceUpdate=False):
		if t is None: t=self.viz.scrubval
		i = int(t/self.viz.refresh.get())-1
		for b in self.bars:
			setbar = b.element.set_width if self.horizontal else b.element.set_height
			setbar(b.data[i])

			if b.err: #Update error bars
				for j,cap in enumerate(b.errPath):
					if len(b.errHist[i]) >= j+1: cap[0 if self.horizontal else 1] = b.errHist[i][j]
		super().draw(t, forceUpdate)

class NetworkPlot(ChartPlot):
	type = 'network'
	def __init__(self, **kwargs):
		if 'prim' not in kwargs: kwargs['prim'] = None
		if 'kind' not in kwargs: kwargs['kind'] = 'edge'
		if 'layout' not in kwargs: kwargs['layout'] = 'spring'
		super().__init__(**kwargs)
		self.ndata = {}

		self.params = {
			'patchColormap': 'Blues',
			#'patchProperty': 'mapcolor', #Don't specify, so we have a default white
			'agentMarker': 'o',
			'agentSize': 30,
			'agentLabel': False,
			'labelSize': 10,
			'labelColor': 'k',
			'labelFamily': 'sans-serif',
			'labelWeight': 'normal',
			'labelAlpha': None,
			'labelAlign': 'center',
			'labelVerticalAlign': 'center',
			'lockLayout': False,
			'patchAspect': 1
		}

	def launch(self, axes):
		import networkx as nx, networkx.drawing.layout as lay, pandas
		def patchgrid_layout(G):
			if not hasattr(self.viz.model, 'patches'): raise
			return {i: data['position'] for i,data in G.nodes.items()}
		lay.patchgrid_layout = patchgrid_layout
		self.nx = nx
		self.pandas = pandas
		self.layClass = getattr(lay, self.layout+'_layout')
		self.components = {}
		axes.set_title(self.label, fontdict={'fontsize':10})

		super().launch(axes)

	#Receives event from MPLVisualization.sendEvent()
	def MPLEvent(self, event):
		if event.name=='key_press_event' and event.key=='l': self.rotateLayout()

		elif event.name=='pick_event':
			pk = list(self.pos.keys())
			agents = [self.viz.model.agent(pk[i]) for i in event.ind]
			self.viz.model.doHooks('agentClick', [agents, self, self.viz.scrubval])

		elif event.name=='button_press_event' and self.layout=='patchgrid':
			self.viz.model.doHooks('patchClick', [self.viz.model.patches[round(event.xdata), round(event.ydata)], self, self.viz.scrubval])

	def update(self, data, t):
		G = self.viz.model.network(self.kind, self.prim, excludePatches=True)

		#Capture label and size data
		if self.params['agentLabel'] and self.params['agentLabel'] != True:
			agents = self.viz.model.allagents
			if 'good:' in self.params['agentLabel']:
				for n in G.nodes: G.nodes[n]['label'] = agents[n].stocks[self.params['agentLabel'].split(':')[1]]
			else:
				for n in G.nodes: G.nodes[n]['label'] = getattr(agents[n],self.params['agentLabel'])
		if self.params['agentSize'] and type(self.params['agentSize']) not in [int, float]:
			agents = self.viz.model.allagents
			if 'good:' in self.params['agentSize']:
				for n in G.nodes: G.nodes[n]['size'] = agents[n].stocks[self.params['agentSize'].split(':')[1]]
			else:
				for n in G.nodes: G.nodes[n]['size'] = getattr(agents[n],self.params['agentSize'])

		self.ndata[t] = G

		#Save spatial data even if we're on a different layout
		if hasattr(self.viz.model, 'patches'):
			pd = self.patchData(None if t==self.viz.model.t else t)
			for col in self.viz.model.patches:
				for p in col:
					p.colorData[t] = pd[p.x][p.y]

			#Renormalize color scale
			nmin, nmax = pd.min().min(), pd.max().max()
			self.normal = plt.cm.colors.Normalize(nmin if not hasattr(self,'normal') or nmin<self.normal.vmin else self.normal.vmin, nmax if not hasattr(self,'normal') or nmax>self.normal.vmax else self.normal.vmax)


	def draw(self, t=None, forceUpdate=False):
		if t is None: t=self.viz.scrubval
		self.axes.clear()
		if self.layout != 'patchgrid': self.axes.axis('off')
		self.axes.set_title(self.label, fontdict={'fontsize':10})

		if self.layout == 'patchgrid':
			pd = self.patchData(t)
			self.components['patches'] = self.axes.imshow(pd, norm=self.normal, cmap=self.params['patchColormap'], aspect=self.params['patchAspect'])
			# self.patchmap.set_norm(self.normal)
			# self.components['patches'].set_data(pd)

		#Draw nodes, edges, and labels separately so we can split out the directed and undirected edges
		self.pos = self.layClass(self.ndata[t])
		sizes = self.params['agentSize']*10 if type(self.params['agentSize']) in [int, float] else [n[1]['size']*10 for n in self.ndata[t].nodes(data=True)]
		self.components['nodes'] = self.nx.draw_networkx_nodes(self.ndata[t], self.pos, ax=self.axes, node_color=[self.viz.model.primitives[n[1]['primitive']].breeds[n[1]['breed']].color.hex for n in self.ndata[t].nodes(data=True)], node_size=sizes, node_shape=self.params['agentMarker'])
		e_directed = [e for e in self.ndata[t].edges.data() if e[2]['directed']]
		e_undirected = [e for e in self.ndata[t].edges.data() if not e[2]['directed']]
		self.components['edges_d'] = self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_directed, width=[e[2]['weight'] for e in e_directed])
		self.components['edges_u'] = self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_undirected, width=[e[2]['weight'] for e in e_undirected], arrows=False)
		if self.params['agentLabel']:
			lab = None if self.params['agentLabel']==True else {n:self.ndata[t].nodes[n]['label'] for n in self.ndata[t].nodes}
			self.components['labels'] = self.nx.draw_networkx_labels(self.ndata[t], self.pos, ax=self.axes, labels=lab, font_size=self.params['labelSize'], font_color=self.params['labelColor'], font_family=self.params['labelFamily'], font_weight=self.params['labelWeight'], alpha=self.params['labelAlpha'], horizontalalignment=self.params['labelAlign'], verticalalignment=self.params['labelVerticalAlign'])

		self.components['nodes'].set_picker(True)	#Listen for mouse events on nodes
		self.components['nodes'].set_pickradius(5)	#Set margin of valid events in pixels

		super().draw(t, forceUpdate)

	def rotateLayout(self):
		self.axes.set_yscale('linear') #Override default logscale keypress
		if self.params['lockLayout']: return

		import networkx.drawing.layout as lay
		layouts = ['spring', 'circular', 'kamada_kawai', 'random', 'shell', 'spectral', 'spiral', 'patchgrid']
		li = layouts.index(self.layout)+1
		while li>=len(layouts): li -= len(layouts)
		self.layout = layouts[li]
		self.layClass = getattr(lay, self.layout+'_layout')

		#kamada_kawai requires scipy
		try: self.draw(self.viz.scrubval)
		except: self.rotateLayout()

	#Helper function
	def getPatchParamValue(self, patch, t=None):
		if t is not None: return patch.colorData[t]
		if 'patchProperty' not in self.params: return 0
		elif 'good:' in self.params['patchProperty']: return patch.stocks[self.params['patchProperty'].split(':')[1]]
		else: return getattr(patch, self.params['patchProperty'])

	def patchData(self, t=None):
		if not hasattr(self.viz.model, 'patches'): return
		#Pandas goes row,col instead of col,row so we have to transpose it
		return self.pandas.DataFrame([[self.getPatchParamValue(p,t) for p in col] for col in self.viz.model.patches]).transpose()

	def config(self, param, val=None):
		if isinstance(param, dict):
			for k,v in param.items(): self.config(k,v)
		elif val is None: return self.params[param]
		else: self.params[param] = val

#======================
# SUB-PLOT OBJECTS
# Mostly sub-plot data will use an Item object, but some need a little more
#======================

class Series(Item):
	@property
	def visible(self):
		if not hasattr(self, 'line'): return self._visible
		elif hasattr(self, 'poly'): return True #If it's a stackplot
		else: return self.line.get_visible()

	@visible.setter
	def visible(self, val):
		if not hasattr(self, 'line'): #If we haven't drawn it yet
			self._visible = val
			return
		elif hasattr(self, 'poly'): return	#Ignore if it's a stackplot

		self.line.set_visible(val)
		for s in self.subseries: s.line.set_visible(val) #Toggle subseries (e.g. percentile bars)
		self.legline.set_alpha(1.0 if val else 0.2)
		self.legtext.set_alpha(1.0 if val else 0.2)

		## Won't work because autoscale_view also includes hidden lines
		## Will have to actually remove and reinstate the line for this to work
		# for g in self.activePlots:
		# 	if c1.series in g.get_lines():
		# 		g.relim()
		# 		g.autoscale_view(tight=True)

		self.line.figure.canvas.draw_idle()

	def toggle(self):
		self.visible = not self.visible

#======================
# HELPER FUNCTIONS
#======================

def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if i%n==0: l.append(k)
		i+=1
	# if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l