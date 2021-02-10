# ==========
# The matplotlib interface for plotting
# Do not run this file; import model.py and run from your file.
# ==========

from numpy import ndarray, asanyarray, log10
from math import sqrt, ceil
import matplotlib, matplotlib.pyplot as plt, matplotlib.style as mlpstyle
from abc import ABC, abstractmethod
from helipad.helpers import *
mlpstyle.use('fast')
import sys

#======================
# TOP-LEVEL VISUALIZERS
# These two use Matplotlib, but subclasses of BaseVisualization don't necessarily have to.
#======================

#Used for creating an entirely new visualization window.
class BaseVisualization:
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
		
		def pause(model, event):
			if model.hasModel and event.canvas is self.fig.canvas:
				if model.running: model.stop()
				else: model.start()
		self.addKeypress(' ', pause)
		
		if isIpy():
			from IPython import get_ipython
			get_ipython().magic('matplotlib widget')
		else: matplotlib.use('TkAgg') #macosx would be preferable (Retina support), but it blocks the cpanel while running
	
	#Subclasses should call super().launch **after** the figure is created.
	@abstractmethod
	def launch(self, title):
		if not isIpy(): self.fig.canvas.set_window_title(title)
		self.fig.tight_layout()
		self.fig.canvas.mpl_connect('close_event', self.model.terminate)
		self.fig.canvas.mpl_connect('key_press_event', self.catchKeypress)
		self.lastUpdate = 0
	
	def addKeypress(self, key, fn):
		if not key in self.keys: self.keys[key] = []
		self.keys[key].append(fn)
	
	def catchKeypress(self, event):
		if event.key in self.keys:
			for f in self.keys[event.key]: f(self.model, event)
	
	@property
	def activePlots(self):
		return {k:plot for k,plot in self.plots.items() if plot.selected}
	
	@property
	def isNull(self):
		return not [plot for plot in self.plots.values() if plot.selected]

class TimeSeries(MPLVisualization):
	def __init__(self, model):
		super().__init__(model)
		self.selector = model.addParameter('plots', 'Plots', 'checkgrid', [], opts={}, runtime=False, config=True)
		
		#Plot categories
		self.addPlot('utility', 'Utility', selected=False)
		
		if len(model.goods) >= 2:
			self.addPlot('demand', 'Demand', selected=False)
			self.addPlot('shortage', 'Shortages', selected=False)
		if model.moneyGood is not None:
			self.addPlot('money', 'Money', selected=False)
		
		#Toggle legend boxes
		#Use event.canvas.figure and not self.fig so it pertains to the current window
		def toggle(model, event):
			for axes in event.canvas.figure.axes:
				leg = axes.get_legend()
				leg.set_visible(not leg.get_visible())
			event.canvas.draw()
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
		if not len(self.activePlots): return #Windowless mode
		
		self.resolution = 1
		self.verticals = []
		if isIpy():
			plt.close() #Clean up after any previous runs
			matplotlib.rcParams['figure.figsize'] = [9, 7]
		
		#fig is the figure, plots is a list of AxesSubplot objects
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(self.activePlots), sharex=True, num=title if isIpy() else None)
		super().launch(title)
		
		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activePlots.values(), plots): plot.launch(axes)
		
		#Resize and position graph window
		fm = self.fig.canvas.manager
		if hasattr(fm, 'window'):
			#This should be the window height, but MPL only allows us to set the figure height.
			#MacOS doesn't let us create a window taller than the screen, but we have to account for
			#the height of the window frame crudely in Windows.
			if sys.platform=='win32': #Respect the taskbar
				import win32api
				for monitor in win32api.EnumDisplayMonitors(): height = .92 * win32api.GetMonitorInfo(monitor[0])['Work'][3]
			else: height = fm.window.winfo_screenheight()
			
			x_px = fm.window.winfo_screenwidth()*2/3
			if x_px + 400 > fm.window.winfo_screenwidth(): x_px = fm.window.winfo_screenwidth()-400
			self.fig.set_size_inches(x_px/self.fig.dpi, height/self.fig.dpi)
			fm.window.wm_geometry("+400+0")
		
		#Style plots
		self.fig.subplots_adjust(hspace=0, bottom=0.05, right=1, top=0.97, left=0.1)
		# plt.setp([a.get_xticklabels() for a in self.fig.axes[:-1]], visible=False)	#What was this for again…?
		self.fig.canvas.mpl_connect('pick_event', self.toggleLine)
		
		self.fig.canvas.draw_idle()
		plt.show(block=False)
	
	def terminate(self, model):
		if self.isNull:
			for p in ['stopafter', 'csv']: model.params[p].enable()
	
	def update(self, data):
		newlen = len(next(data[x] for x in data))
		if (self.resolution > 1): data = {k: keepEvery(v, self.resolution) for k,v in data.items()}
		time = newlen + len(next(iter(self.activePlots.values())).series[0].fdata)*self.resolution
		
		#Append new data to cumulative series
		for plot in self.activePlots.values():
			for serie in plot.series:
				if callable(serie.reporter):						#Lambda functions
					for i in range(int(newlen/self.resolution)):
						serie.fdata.append(serie.reporter(time-newlen+(1+i)*self.resolution))
				elif serie.reporter in data: serie.fdata += data[serie.reporter] #Actual data
				else: continue									#No data
		
		#Redo resolution at 2500, 25000, etc
		if 10**(log10(time/2.5)-3) >= self.resolution:
			self.resolution *= 10
			for plot in self.activePlots.values():
				for serie in plot.series:
					serie.fdata = keepEvery(serie.fdata, 10)
		
		#Update the actual graphs. Has to be after the new resolution is set
		tseries = range(0, time, self.resolution)
		for plot in self.activePlots.values():
			#No way to update the stack (?) so redraw it from scratch
			if plot.stack:
				lines = plot.axes.stackplot(tseries, *[s.fdata for s in plot.series], colors=[s.color.hex for s in plot.series])
				for series, poly in zip(plot.series, lines): series.poly = poly
			else:
				for serie in plot.series:
					serie.line.set_ydata(serie.fdata)
					serie.line.set_xdata(tseries)
				plot.axes.relim()
				plot.axes.autoscale_view(tight=False)
			
			#Prevent decaying averages on logscale graphs from compressing the entire view
			ylim = plot.axes.get_ylim()
			if plot.axes.get_yscale() == 'log' and ylim[0] < 10**-6: plot.axes.set_ylim(bottom=10**-6)
		
		if self.resolution > self.model.param('refresh'): self.model.param('refresh', self.resolution)
		if self.fig.stale: self.fig.canvas.draw_idle()
		self.fig.canvas.start_event_loop(0.0001) #Listen for user input
	
	def toggleLine(self, event):
		c1 = event.artist					#The label or line that was clicked
		if len(c1.series._x) == 0: return	#Ignore if it's a stackplot
		vis = not c1.series.get_visible()
		c1.series.set_visible(vis)
		for s in c1.series.subseries: s.line.set_visible(vis) #Toggle subseries (e.g. percentile bars)
		c1.set_alpha(1.0 if vis else 0.2)
		c1.otherComponent.set_alpha(1.0 if vis else 0.2)

		## Won't work because autoscale_view also includes hidden lines
		## Will have to actually remove and reinstate the line for this to work
		# for g in self.activePlots:
		# 	if c1.series in g.get_lines():
		# 		g.relim()
		# 		g.autoscale_view(tight=True)
		
		self.fig.canvas.draw()
	
	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, selected=True, logscale=False, stack=False):
		plot = Plot(model=self.model, name=name, label=label, series=[], logscale=logscale, stack=stack)
		
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
		if getattr(self.model, 'cpanel', False): raise RuntimeError('Cannot remove plots after control panel is drawn')
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return
		
		if not name in self.plots:
			warnings.warn('No plot \''+name+'\' to remove', None, 2)
			return False
				
		if reassign is not None: self.plots[reassign].series += self.plots[name].series
		del self.plots[name]
		del self.selector.opts[name]
		del self.selector.vars[name]
		if name in self.selector.default: self.selector.default.remove(name)
		return True
	
	def event(self, t, color='#CC0000', linestyle='--', linewidth=1, **kwargs):
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.activePlots.values()])
		
		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.plots.values())).axes.text(t, 0, label, horizontalalignment='center')

class Charts(MPLVisualization):
	def __init__(self, model):
		super().__init__(model)
		self.events = {}
		self.plotTypes = {}
				
		for p in [BarChart, NetworkPlot]: self.addPlotType(p)
		model.params['refresh'].runtime=False
		self.refresh = model.params['refresh']
		self.model = model # :(
	
	def launch(self, title):
		if not len(self.activePlots): return #Windowless mode
		from matplotlib.widgets import Slider
		
		n = len(self.activePlots)
		x = ceil(sqrt(n))
		y = ceil(n/x)
		if isIpy():
			plt.close() #Clean up after any previous runs
			matplotlib.rcParams['figure.figsize'] = [9, 7]
		
		#Add the subplots individually rather than using plt.subplots() so we can mix and match projections
		self.fig = plt.figure()
		plots = list(self.activePlots.values())
		for i in range(n):
			plots[i].launch(self.fig.add_subplot(y,x,i+1, projection=plots[i].projection))
		super().launch(title)
		
		#Resize and position graph window
		fm = self.fig.canvas.manager
		if hasattr(fm, 'window'):
			#This should be the window height, but MPL only allows us to set the figure height.
			#MacOS doesn't let us create a window taller than the screen, but we have to account for
			#the height of the window frame crudely in Windows.
			if sys.platform=='win32': #Respect the taskbar
				import win32api
				for monitor in win32api.EnumDisplayMonitors(): height = .92 * win32api.GetMonitorInfo(monitor[0])['Work'][3]
			else: height = fm.window.winfo_screenheight()
			
			x_px = fm.window.winfo_screenwidth()*2/3
			if x_px + 400 > fm.window.winfo_screenwidth(): x_px = fm.window.winfo_screenwidth()-400
			self.fig.set_size_inches(x_px/self.fig.dpi, height/self.fig.dpi)
			fm.window.wm_geometry("+400+0")
		
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
		
		#Update slider. This calls self.scrub()
		self.timeslider.valmax = t
		self.timeslider.set_val(t)
		self.timeslider.ax.set_xlim(0,t) #Refresh
		
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')
		if self.fig.stale: self.fig.canvas.draw_idle()
		self.fig.canvas.start_event_loop(0.0001) #Listen for user input
	
	#Update the graph to a particular model time
	def scrub(self, t):
		self.scrubval = t
		for c in self.activePlots.values(): c.draw(t)
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')
	
	def addPlot(self, name, label, type=None, **kwargs):
		self.type = type if type is not None else 'bar'
		if not self.type in self.plotTypes: raise KeyError('\''+self.type+'\' is not a registered plot visualizer.')
		self.plots[name] = self.plotTypes[self.type](name=name, label=label, selected=True, viz=self, **kwargs)
		return self.plots[name]
	
	def addPlotType(self, clss):
		if not issubclass(clss, ChartPlot): raise TypeError('New plot types must subclass ChartPlot.')
		self.plotTypes[clss.type] = clss
	
	def removePlot(self, name):
		if getattr(self.model, 'cpanel', False): raise RuntimeError('Cannot remove plots after control panel is drawn')
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return
		
		if not name in self.plots:
			warnings.warn('No plot \''+name+'\' to remove', None, 2)
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

class Plot(Item):
	@property
	def selected(self): return self.model.params['plots'].get(self.name)

	@selected.setter
	def selected(self, val): self.active(val)

	def active(self, val, updateGUI=True):
		self.model.params['plots'].set(self.name, bool(val))
		if updateGUI and not isIpy() and hasattr(self, 'check'):
			self.check.set(val)

	#First arg is a reporter name registered in DataCollector, or a lambda function
	#Second arg is the series name. Use '' to not show in the legend.
	#Third arg is the plot's hex color, or a Color object
	def addSeries(self, reporter, label, color, style='-'):
		if not isinstance(color, Color): color = Color(color)

		#Check against columns and not reporters so subseries work
		if not callable(reporter) and not reporter in self.model.data.columns:
			raise KeyError('Reporter \''+reporter+'\' does not exist. Be sure to register reporters before adding series.')

		#Add subsidiary series (e.g. percentile bars)
		subseries = []
		if reporter in self.model.data.reporters and self.model.data.reporters[reporter].children:
			for p in self.model.data.reporters[reporter].children:
				if '-unsmooth' in p: continue #Don't plot the unsmoothed series
				subseries.append(self.addSeries(p, '', color.lighten(), style='--'))

		#Since many series are added at setup time, we have to de-dupe
		for s in self.series:
			if s.reporter == reporter:
				self.series.remove(s)

		series = Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=self.name)
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
			series.line.subseries = series.subseries
			series.line.label = series.label
	
		#Set up the legend for click events on both the line and the legend
		leg = axes.legend(loc='upper right')
		for legline, label in zip(leg.get_lines(), leg.get_texts()):
			legline.set_picker(True)	#Listen for mouse events on the legend line
			legline.set_pickradius(5)	#Set margin of valid events in pixels
			label.set_picker(5)			#Do both on the legend text
			for s in self.series:
				if s.label==label.get_text():
					label.series = s.line
					legline.series = s.line
					legline.otherComponent = label
					label.otherComponent = legline
					break

#Used for creating a synchronic plot area in the Charts visualizer. Must interface with Matplotlib and specify class.type.
#Extra kwargs in Charts.addPlot() are passed to ChartPlot.__init__().
class ChartPlot(Item):
	def __init__(self, **kwargs):
		if not 'projection' in kwargs and not hasattr(self, 'projection'): self.projection = None
		super().__init__(**kwargs)
	
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
		if not 'prim' in kwargs: kwargs['prim'] = None
		if not 'kind' in kwargs: kwargs['kind'] = 'edge'
		if not 'layout' in kwargs: kwargs['layout'] = 'spring'
		super().__init__(**kwargs)
		self.ndata = {}
	
	def launch(self, axes):
		import networkx as nx, networkx.drawing.layout as lay
		self.nx = nx
		self.layClass = getattr(lay, self.layout+'_layout')
		super().launch(axes)
		
		def agentEvent(event):
			pk = list(self.pos.keys())
			agents = [self.viz.model.agent(pk[i]) for i in event.ind]
			self.viz.model.doHooks('networkNodeClick', [agents, self, self.viz.scrubval])
		self.viz.fig.canvas.mpl_connect('pick_event', agentEvent)
		
		def rotateNetworkLayout(model, event):
			if self.axes is event.inaxes: self.rotateLayout()
		self.viz.addKeypress('l', rotateNetworkLayout)

	def update(self, data, t):
		G = self.viz.model.network(self.kind, self.prim)
		self.ndata[t] = G

	def draw(self, t=None, forceUpdate=False):
		if t is None: t=self.viz.scrubval
		self.axes.clear()
		self.axes.axis('off')
		self.axes.set_title(self.label, fontdict={'fontsize':10})
		
		#Draw nodes, edges, and labels separately so we can split out the directed and undirected edges
		self.pos = self.layClass(self.ndata[t])
		nodes = self.nx.draw_networkx_nodes(self.ndata[t], self.pos, ax=self.axes, node_color=[self.viz.model.primitives[n[1]['primitive']].breeds[n[1]['breed']].color.hex for n in self.ndata[t].nodes(data=True)])
		e_directed = [e for e in self.ndata[t].edges.data() if e[2]['directed']]
		e_undirected = [e for e in self.ndata[t].edges.data() if not e[2]['directed']]
		self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_directed, width=[e[2]['weight'] for e in e_directed])
		self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_undirected, width=[e[2]['weight'] for e in e_undirected], arrows=False)
		self.nx.draw_networkx_labels(self.ndata[t], self.pos, ax=self.axes)
		
		nodes.set_picker(True)	#Listen for mouse events on nodes
		nodes.set_pickradius(5)	#Set margin of valid events in pixels
		super().draw(t, forceUpdate)
	
	def rotateLayout(self):
		self.axes.set_yscale('linear')
		import networkx.drawing.layout as lay
		layouts = ['spring', 'circular', 'kamada_kawai', 'random', 'shell', 'spectral', 'spiral']
		li = layouts.index(self.layout)+1
		while li>=len(layouts): li -= len(layouts)
		self.layout = layouts[li]
		self.layClass = getattr(lay, self.layout+'_layout')
		
		#kamada_kawai requires scipy
		try: self.draw(self.viz.scrubval)
		except: self.rotateLayout()

#======================
# HELPER FUNCTIONS
#======================
	
def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l