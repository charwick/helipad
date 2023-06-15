"""
Base classes for visualizing Helipad models with Matplotlib, to be passed to `model.useVisual()`. Main visualizers are `TimeSeries` to display diachronic data, and `Charts` to display synchronic data.
"""

import sys
from abc import ABC, abstractmethod
from math import sqrt, ceil, pi, isnan
from numpy import ndarray, array, asanyarray, log10, linspace, newaxis, arange, full_like, linalg, ones, vstack
import matplotlib, matplotlib.pyplot as plt, matplotlib.style as mlpstyle, matplotlib.cm as cm
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
from helipad.helpers import *
mlpstyle.use('fast')

#======================
# TOP-LEVEL VISUALIZERS
# These two use Matplotlib, but subclasses of BaseVisualization don't necessarily have to
#======================

class BaseVisualization(ABC):
	"""Base class defining the methods that must be implemented by any visualization. https://helipad.dev/functions/basevisualization/"""
	isNull: bool = True

	@abstractmethod
	def launch(self, title: str):
		"""Launch the visualization window (if in Tkinter) or cell (if in Jupyter). https://helipad.dev/functions/basevisualization/launch/"""

	@abstractmethod
	def refresh(self, data: dict):
		"""Update the visualization with new data and refresh the display. `data` is only data since the last visualization refresh. https://helipad.dev/functions/basevisualization/refresh/"""

	@abstractmethod
	def event(self, t: int, color, **kwargs):
		"""Called when an event is triggered, in order to be reflected in the visualization. https://helipad.dev/functions/basevisualization/event/"""

	def terminate(self, model):
		"""Cleanup on model termination. Called automatically from `model.terminate()`. https://helipad.dev/functions/basevisualization/terminate/"""

class MPLVisualization(BaseVisualization, dict):
	"""Base class for visualizations using Matplotlib. https://helipad.dev/functions/mplvisualization/"""

	def __init__(self, model):
		self.model = model #Unhappy with this
		self.selector = model.params.add('plots', ï('Plots'), 'checkgrid', [], opts={}, runtime=False, config=True)
		self.dim = None
		self.pos = (400, 0)
		self.fig = None
		self.lastUpdate = None
		self.keyListeners = {}

		def pause(model, event):
			if model.hasModel and event.canvas is self.fig.canvas:
				if model.running: model.stop()
				else: model.start()
		self.addKeypress(' ', pause)

		if isNotebook():
			from IPython import get_ipython
			get_ipython().magic('matplotlib widget')
		else: matplotlib.use('TkAgg') #macosx would be preferable (Retina support), but it blocks the cpanel while running

	def __repr__(self): return f'<{self.__class__.__name__} with {len(self)} plots>'

	# Subclasses should call super().launch **after** the figure is created.
	@abstractmethod
	def launch(self, title: str):
		if not isNotebook():
			self.fig.canvas.manager.set_window_title(title)
			if self.model.cpanel: self.model.cpanel.setAppIcon()

		#MPL can't take a method bound to an unhashable class (i.e. `dict`)
		def sendEvent(event):
			axes = event.artist.axes if hasattr(event, 'artist') else event.inaxes
			if axes is not None:
				for p in self.activePlots.values():
					if axes is p.axes:
						p.MPLEvent(event)
						break

			if event.name=='key_press_event' and event.key in self.keyListeners:
				for f in self.keyListeners[event.key]: f(self.model, event)

		self.fig.tight_layout()
		self.fig.canvas.mpl_connect('close_event', self.model.terminate)
		self.fig.canvas.mpl_connect('key_press_event', sendEvent)
		self.fig.canvas.mpl_connect('pick_event', sendEvent)
		self.fig.canvas.mpl_connect('button_press_event', sendEvent)
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

	#Save window dimensions and position
	def terminate(self, model):
		fm = self.fig.canvas.manager
		if hasattr(fm, 'window'):
			self.dim = list(self.fig.get_size_inches()*self.fig.dpi)
			pos = fm.window.wm_geometry().split('+')
			self.pos = (pos[1], pos[2])

	def addKeypress(self, key: str, fn):
		"""Register a function to be run when `key` is pressed in a Matplotlib visualizer. `fn` will run if `key` is pressed at any time when the plot window is in focus. To narrow the focus to a particular plot, define `catchKeypress()` in a subclass of `ChartPlot`. https://helipad.dev/functions/mplvisualization/addkeypress/"""
		if not key in self.keyListeners: self.keyListeners[key] = []
		self.keyListeners[key].append(fn)

	@property
	def activePlots(self) -> dict:
		"""The subset of the plots containing the `Plot`s that are currently active. https://helipad.dev/functions/mplvisualization/#activePlots"""
		return {k:plot for k,plot in self.items() if plot.selected}

	@property
	def isNull(self) -> bool:
		"""`True` when the model should run as-if with no visualization, for example if all plots are unselected. `False` indicates the window can be launched. https://helipad.dev/functions/mplvisualization/#isNull"""
		return not [plot for plot in self.values() if plot.selected]

	@property
	def plots(self):
		"""A `dict` of plots. This property is deprecated; the visualization object can be indexed directly."""
		warnings.warn(ï('model.visual.plots is deprecated. Plots can be accessed by indexing the visualization object directly.'), FutureWarning, 2)
		return self

class TimeSeries(MPLVisualization):
	"""A Matplotlib-based visualizer for displaying time series data on plots so the whole history of any given variable over the model's runtime can be seen at once. https://helipad.dev/functions/timeseries/"""
	def __init__(self, model):
		super().__init__(model)
		self.verticals = []

		#Plot categories
		self.addPlot('utility', 'Utility', selected=False)

		if len(model.goods) >= 2: self.addPlot('demand', ï('Demand'), selected=False)
		if model.goods.money is not None: self.addPlot('money', ï('Money'), selected=False)

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
			for p in self.values():
				for s in p.series:
					if s.reporter==key:
						# Remove subseries
						for ss in s.subseries:
							for sss in self[s.plot].series:
								if sss.reporter == ss:
									self[s.plot].series.remove(sss)
									continue
						self[s.plot].series.remove(s)

		#Move the plots parameter to the end when the cpanel launches
		@model.hook('CpanelPreLaunch')
		def movePlotParam(model):
			model.params['plots'] = model.params.pop('plots')

	def launch(self, title: str):
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
		super().terminate(model)
		if self.isNull:
			model.params['csv'].enable()
			if not isinstance(model.param('stopafter'), str): model.params['stopafter'].enable()

	def refresh(self, data: dict):
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

	def addPlot(self, name: str, label: str, position=None, selected: bool=True, logscale: bool=False, stack: bool=False):
		"""Register a plot area in the `TimeSeries` plot area to which data series can be added. `position` Position is the number you want it to be, *not* the array position. https://helipad.dev/functions/timeseries/addplot/"""
		plot = TimeSeriesPlot(viz=self, name=name, label=label, logscale=logscale, stack=stack)

		self.selector.addItem(name, label, position, selected)
		if position is None or position > len(self): self[name] = plot
		else:		#Reconstruct the dicts because there's no insert method…
			newplots, i = ({}, 1)
			for k,v in self.items():
				if position==i:
					newplots[name] = plot
				newplots[k] = v
				i+=1
			self.clear()
			self.update(newplots)

		plot.selected = selected #Do this after CheckgridParam.addItem
		return plot

	def removePlot(self, name, reassign=None):
		"""Remove a plot or plots and optionally reassign their series to a different plot. https://helipad.dev/functions/timeseries/removeplot/"""
		if self.model.cpanel: raise RuntimeError(ï('Cannot remove plots after control panel is drawn.'))
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return

		if not name in self:
			warnings.warn(ï('No plot \'{}\' to remove.').format(name), None, 2)
			return False

		if reassign is not None: self[reassign].series += self[name].series
		del self[name]
		del self.selector.opts[name]
		del self.selector.vars[name]
		if name in self.selector.default: self.selector.default.remove(name)
		return True

	def event(self, t: int, color='#CC0000', linestyle: str='--', linewidth=1, **kwargs):
		if self.fig is None: return
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.activePlots.values()])

		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.values())).axes.text(t, 0, label, horizontalalignment='center')

class Charts(MPLVisualization):
	"""A Matplotlib-based visualizer for a variety of visualizations that display data that reflects a single point in time. https://helipad.dev/functions/charts/"""
	def __init__(self, model):
		super().__init__(model)
		self.events = {}
		self.plotTypes = {}

		for p in [BarChart, AgentsPlot, TimeSeriesPlot]: self.addPlotType(p)
		model.params['refresh'].runtime=False
		self.model = model # :(

	def launch(self, title: str):
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
			plots[i].subplot_position = (y,x,i+1)
		super().launch(title)

		#Time slider
		ref = self.model.params['refresh'].get()
		self.fig.subplots_adjust(bottom=0.12) #Make room for the slider
		sax = self.fig.add_axes([0.1,0.01,.75,0.03], facecolor='#EEF')
		self.timeslider = Slider(sax, 't=', 0, ref, ref, valstep=ref, closedmin=False)
		self.timeslider.on_changed(self.scrub)

		self.fig.canvas.draw_idle()
		plt.show(block=False)

	def refresh(self, data: dict):
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

	def scrub(self, t: int):
		"""Update the visualizer with the values from model time `t`."""
		self.scrubval = t
		for c in self.activePlots.values(): c.draw(t)
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')

	def addPlot(self, name: str, label: str, type=None, position=None, selected=True, **kwargs):
		"""Adds a plot area to the Chart visualizer. Defaults to a bar chart, but can be set to any subclass of ChartPlot. Kwargs are passed to the `ChartPlot` object. https://helipad.dev/functions/charts/addplot/"""
		self.selector.addItem(name, label, position, selected)
		if type == 'network': #Deprecated in Helipad 1.6; remove in 1.8
			warnings.warn(ï('The `network` plot type is deprecated. Use `agents` instead.'), FutureWarning, 2)
			type = 'agents'
		self.type = type if type is not None else 'bar'
		if self.type not in self.plotTypes: raise KeyError(ï('\'{}\' is not a registered plot visualizer.').format(self.type))
		self[name] = self.plotTypes[self.type](name=name, label=label, viz=self, selected=True, **kwargs)

		self[name].selected = selected #Do this after CheckgridParam.addItem
		return self[name]

	def addPlotType(self, clss):
		"""Registers a new plot type for the Charts visualizer. Registered plot types can then be added to the visualization area with `Charts.addPlot()`. https://helipad.dev/functions/charts/addplottype/"""
		if not issubclass(clss, ChartPlot): raise TypeError(ï('New plot types must subclass ChartPlot.'))
		self.plotTypes[clss.type] = clss

	def removePlot(self, name):
		"""Remove a plot or plots and optionally reassign their series to a different plot. https://helipad.dev/functions/timeseries/removeplot/"""
		if self.model.cpanel: raise RuntimeError(ï('Cannot remove plots after control panel is drawn.'))
		if isinstance(name, list):
			for p in name: self.removePlot(p)
			return

		if not name in self:
			warnings.warn(ï('No plot \'{}\' to remove.').format(name), None, 2)
			return False

		del self[name]
		return True

	def event(self, t: int, color='#FDC', **kwargs):
		ref = self.model.params['refresh'].get()
		self.events[ceil(t/ref)*ref] = color

#======================
# PLOT-LEVEL VISUALIZERS
# Plug into either TimeSeries or Charts as one of the subplots
#======================

class ChartPlot(Item):
	"""Base class for creating a synchronic plot area in the Charts visualizer. Must interface with Matplotlib and specify `class.type`. Extra kwargs in `Charts.addPlot()` are passed to `ChartPlot.__init__()`. https://helipad.dev/functions/chartplot/"""
	def __init__(self, **kwargs):
		if 'projection' not in kwargs and not hasattr(self, 'projection'): self.projection = None
		self.axes = None
		super().__init__(**kwargs)

	def __repr__(self): return f'<{self.__class__.__name__}: {self.name}>'

	@property
	def selected(self):
		"""Whether the plot is currently queued for display. Do not modify this property directly; use ChartPlot.active() to ensure consistency with the GUI state. https://helipad.dev/functions/chartplot/#selected"""
		return self.viz.model.params['plots'].get(self.name)

	@selected.setter
	def selected(self, val: bool): self.active(val)

	def active(self, val: bool, updateGUI: bool=True):
		"""Turn on or off the selected state of a plot in the control panel. https://helipad.dev/functions/chartplot/active/"""
		self.viz.model.params['plots'].set(self.name, bool(val))
		if updateGUI and not isNotebook() and hasattr(self, 'check'):
			self.check.set(val)

	@abstractmethod
	def launch(self, axes):
		"""Set up the plot's `axes` object when `Charts` launches the visualization window. Subclasses should call `super().launch(axes)` at the beginning of the method. https://helipad.dev/functions/chartplot/launch/"""
		self.axes = axes
		axes.set_title(self.label, fontdict={'fontsize':10})

	@abstractmethod
	def update(self, data: dict, t: int):
		"""Receive current model data and store it for future scrubbing. Values of `data` should only contain the most recent value of each column. This method is only for updating plot data; drawing code happens in `draw()`. https://helipad.dev/functions/chartplot/update/"""

	@abstractmethod
	def draw(self, t: int, forceUpdate: bool=False):
		"""Refresh the `axes` object to display new or historical data. This method is called after `ChartPlot.update()` when the visualizer receives new data, and when scrubbing the time bar. https://helipad.dev/functions/chartplot/draw/"""
		if forceUpdate: self.viz.fig.canvas.draw_idle()

	def remove(self):
		"""Removes the plot from the visualizer."""
		self.viz.removePlot(self.name)

	def MPLEvent(self, event):
		"""Catch `pick_event`, `key_press_event`, and `button_press_event` events that occur inside a particular plot. https://helipad.dev/functions/chartplot/mplevent/"""

class TimeSeriesPlot(ChartPlot):
	"""Visualize time series data on one or more variables. Can be used in either the `TimeSeries` or `Charts` visualizer. https://helipad.dev/functions/timeseriesplot/"""
	type = 'timeseries'
	def __init__(self, **kwargs):
		self.series = []
		self.scrubline = None
		for p in ['logscale', 'stack']:
			if p not in kwargs: kwargs[p] = False
		super().__init__(**kwargs)

	def addSeries(self, reporter, label: str, color, style: str='-', visible: bool=True):
		"""Register a reporter to be plotted during the model's runtime. https://helipad.dev/functions/timeseriesplot/addseries/"""
		if not isinstance(color, Color): color = Color(color)

		#Check against columns and not reporters so subseries work
		if not callable(reporter) and not reporter in self.viz.model.data.columns:
			raise KeyError(ï('Reporter \'{}\' does not exist. Be sure to register reporters before adding series.').format(reporter))

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

	def update(self, data: dict, t: str):
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

	def draw(self, t: int, forceUpdate: bool=False):
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
	def resolution(self) -> int:
		"""The time elapsing between any two data points drawn to screen (not the time elapsing between two updates, which is a user-controlled parameter)."""
		return self.viz.resolution if hasattr(self.viz, 'resolution') else int(self.viz.model.param('refresh'))

class BarChart(ChartPlot):
	"""A plot type that displays live-updating bar charts. https://helipad.dev/functions/barchart/"""
	type = 'bar'
	def __init__(self, **kwargs):
		for arg in ['horizontal', 'logscale']:
			if not arg in kwargs: kwargs[arg] = False
		super().__init__(**kwargs)
		self.bars = []

	def addBar(self, reporter, label: str, color='blue', position=None):
		"""Register a data reporter as a bar on the current plot. To display error bars, use the `std` or `percentiles` arguments when creating the agent reporter. https://helipad.dev/functions/barchart/addbar/"""
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

		#Set bar names
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

	def update(self, data: dict, t: int):
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

	def draw(self, t: int=None, forceUpdate: bool=False):
		if t is None: t=self.viz.scrubval
		i = int(t/self.viz.model.param('refresh'))-1
		for b in self.bars:
			setbar = b.element.set_width if self.horizontal else b.element.set_height
			setbar(b.data[i])

			if b.err: #Update error bars
				for j,cap in enumerate(b.errPath):
					if len(b.errHist[i]) >= j+1: cap[0 if self.horizontal else 1] = b.errHist[i][j]
		super().draw(t, forceUpdate)

class AgentsPlot(ChartPlot):
	"""A plot visualizer used for displaying individual agents in various layouts. Agents can be plotted in a network structure, a spatial layout (or both at once), or a scatterplot comparing agents on two data dimensions. https://helipad.dev/functions/agentsplot/"""
	type = 'agents'
	def __init__(self, **kwargs):
		if 'prim' not in kwargs: kwargs['prim'] = None
		if 'kind' in kwargs:
			warnings.warn(ï('The kind= argument is deprecated and has been replaced with network=.')) #Deprecated in Helipad 1.6; remove in Helipad 1.8
			kwargs['network'] = kwargs['kind']
		if 'network' not in kwargs: kwargs['network'] = 'edge'
		if 'layout' not in kwargs: kwargs['layout'] = 'scatter' if 'scatter' in kwargs else 'spring'
		if 'scatter' not in kwargs: kwargs['scatter'] = None
		super().__init__(**kwargs)
		self.scatterLims = [[0,0],[0,0]]
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
			'patchAspect': 1,
			'mapBg': 'black',
			'regLine': False,
			'regColor': 'red',
			'regWidth': 1
		}

	def launch(self, axes):
		import networkx as nx, networkx.drawing.layout as lay
		self.layouts = {l: getattr(lay, l+'_layout') for l in ['spring', 'circular', 'kamada_kawai', 'random', 'shell', 'spectral', 'spiral']}

		def spatial_layout(G):
			if self.projection == 'polar': #Calculate the right angle from the x coordinate without modifying the original tuples
				return {i: (2*pi-(2*pi/self.viz.model.patches.dim[0] * data['position'][0])+1/2*pi, data['position'][1]) for i, data in G.nodes.items()}
			else: return {i: data['position'] for i,data in G.nodes.items()}

		def scatter_layout(G):
			self.axes.set_xlabel(self.scatter[0])
			self.axes.set_ylabel(self.scatter[1])
			self.axes.spines['top'].set_visible(False)
			self.axes.spines['right'].set_visible(False)
			data = {i: [data[self.scatter[0]], data[self.scatter[1]]] for i,data in G.nodes.items()}

			#Update limits if necessary
			xs, ys = array([d[0] for d in data.values()]), array([d[1] for d in data.values()])
			self.scatterLims[0][0] = min(self.scatterLims[0][0], xs.min())
			self.scatterLims[0][1] = max(self.scatterLims[0][1], xs.max())
			self.scatterLims[1][0] = min(self.scatterLims[1][0], ys.min())
			self.scatterLims[1][1] = max(self.scatterLims[1][1], ys.max())
			self.axes.set_xlim(*self.scatterLims[0])
			self.axes.set_ylim(*self.scatterLims[1])

			#Add regression line if applicable
			if self.params['regLine']:
				b0, b1 = linalg.lstsq(vstack([xs, ones(len(xs))]).T, ys, rcond=None)[0]
				self.axes.add_line(Line2D(
					[self.scatterLims[0][0], self.scatterLims[0][1]], [b0*self.scatterLims[0][0]+b1, b0*self.scatterLims[0][1]+b1],
					linestyle = '--' if self.params['regLine'] is True else self.params['regLine'],
					color = self.params['regColor'],
					linewidth = self.params['regWidth']
			    ))

			return data
		self.layouts['spatial'] = spatial_layout
		self.layouts['scatter'] = scatter_layout

		self.nx = nx
		self.components = {}

		super().launch(axes)

	def MPLEvent(self, event):
		if event.name=='key_press_event' and event.key=='l': self.rotateLayout()

		elif event.name=='pick_event':
			pk = list(self.pos.keys())
			agents = [self.viz.model.agents[pk[i]] for i in event.ind]
			self.viz.model.doHooks('agentClick', [agents, self, self.viz.scrubval])

		elif event.name=='button_press_event' and self.layout=='spatial':
			if self.projection=='polar':
				x = 2*pi-event.xdata+1/2*pi
				if x > 2*pi: x-=2*pi
				x,y = x/(2*pi/self.viz.model.patches.dim[0]), event.ydata
			else:
				x,y = event.xdata, event.ydata
			if x > self.viz.model.patches.boundaries[0][1] or y > self.viz.model.patches.boundaries[1][1]: return
			self.viz.model.doHooks('patchClick', [self.viz.model.patches.at(x,y), self, self.viz.scrubval])

	def update(self, data: dict, t: int):
		G = self.viz.model.agents.network(self.network, self.prim, excludePatches=self.prim!='patch')

		#Capture data for label, size, and scatterplot position
		capture = {}
		if self.params['agentLabel'] and self.params['agentLabel'] is not True: capture['label'] = self.params['agentLabel']
		if self.params['agentSize'] and type(self.params['agentSize']) not in [int, float]: capture['size'] = self.params['agentSize']
		if self.scatter:
			for v in self.scatter: capture[v] = v
		agents = {a.id:a for a in (self.viz.model.agents[self.prim] if self.prim else self.viz.model.agents.all)}
		for k,v in capture.items():
			if 'good:' in v:
				for n in G.nodes: G.nodes[n][k] = agents[n].stocks[v.split(':')[1]]
			else:
				for n in G.nodes: G.nodes[n][k] = getattr(agents[n],v)
		self.ndata[t] = G

		#Save spatial data even if we're on a different layout
		if self.viz.model.patches:
			lst = []
			for p in self.viz.model.agents['patch']:
				p.colorData[t] = self.getPatchParamValue(p, None if t==self.viz.model.t else t)
				lst.append(p.colorData[t])

			#Renormalize color scale
			nmin, nmax = min(lst), max(lst)
			self.normal = plt.cm.colors.Normalize(nmin if not hasattr(self,'normal') or nmin<self.normal.vmin else self.normal.vmin, nmax if not hasattr(self,'normal') or nmax>self.normal.vmax else self.normal.vmax)

	def draw(self, t: int=None, forceUpdate: bool=False):
		if t is None: t=self.viz.scrubval
		self.axes.clear()
		if self.layout not in ['spatial', 'scatter'] or self.projection=='polar': self.axes.axis('off')
		self.axes.set_title(self.label, fontdict={'fontsize':10})
		if self.layout != 'spatial' or self.viz.model.patches.geometry != 'geo':
			self.axes.set_facecolor('white')
			self.axes.set_aspect('auto')
		self.pos = self.layouts[self.layout](self.ndata[t])

		if self.layout == 'spatial':
			cmap = cm.get_cmap(self.params['patchColormap'])
			if self.viz.model.patches.geometry == 'geo': pd = array([self.getPatchParamValue(p,t) for p in self.viz.model.patches])
			else:
				pd = array([[self.getPatchParamValue(p,t) for p in col] for col in self.viz.model.patches]).T #Transpose because numpy is indexed col, row
			if self.projection=='polar':
				self.axes.set_aspect('equal')
				self.axes.set_ylim(0, self.viz.model.patches.dim[1])
				norm = (pd - int(self.normal.vmin))/(rng if (rng:=(self.normal.vmax-int(self.normal.vmin))) else 1)
				space = linspace(0.0, 1.0, 100)
				rgb = cmap(space)[newaxis, :, :3][0]

				x = self.viz.model.patches.dim[0]
				for r in range(len(norm)):
					for ti in range(len(norm[0])):
						#Define the range going counterclockwise. The 1/4 is to make r=0 point north rather than east.
						#Last argument is the resolution of the curve
						theta = arange(2*pi*((1-1/x) * ti - 1/x + 1/4), 2*pi*((1-1/x) * ti + 1/4)+.04, .04)
						color = self.params['mapBg'] if isnan(norm[r, ti]) else rgb[int(norm[r,ti]*(len(space)-1))]
						self.axes.fill_between(theta, full_like(theta, r), full_like(theta, r+1), color=color)
			else:
				if self.viz.model.patches.geometry == 'rect':
					self.axes.spines['top'].set_visible(True)
					self.axes.spines['right'].set_visible(True)
					cmap.set_bad(self.params['mapBg'])
					self.components['patches'] = self.axes.imshow(pd, norm=self.normal, cmap=cmap, aspect=self.params['patchAspect'])
					# self.patchmap.set_norm(self.normal)
					# self.components['patches'].set_data(pd)
				elif self.viz.model.patches.geometry == 'geo':
					self.axes.set_aspect('equal')
					self.axes.set_xlim(*self.viz.model.patches.boundaries[0])
					self.axes.set_ylim(*self.viz.model.patches.boundaries[1])
					self.axes.set_facecolor(self.params['mapBg'])
					norm = (pd - int(self.normal.vmin))/(rng if (rng:=(self.normal.vmax-int(self.normal.vmin))) else 1)
					space = linspace(0.0, 1.0, 100)
					rgb = cmap(space)[newaxis, :, :3][0]
					for i,p in enumerate(self.viz.model.patches):
						color = self.params['mapBg'] if isnan(norm[i]) else rgb[int(norm[i]*(len(space)-1))]
						self.axes.add_patch(Polygon(array(p.polygon.exterior.xy).T, color=color))

		#Draw nodes, edges, and labels separately so we can split out the directed and undirected edges
		sizes = self.params['agentSize']*10 if type(self.params['agentSize']) in [int, float] else [n[1]['size']*10 for n in self.ndata[t].nodes(data=True)]
		self.components['nodes'] = self.nx.draw_networkx_nodes(self.ndata[t], self.pos, ax=self.axes, node_color=[self.viz.model.agents[n[1]['primitive']].breeds[n[1]['breed']].color.hex for n in self.ndata[t].nodes(data=True)], node_size=sizes, node_shape=self.params['agentMarker'])
		e_directed = [e for e in self.ndata[t].edges.data() if e[2]['directed']]
		e_undirected = [e for e in self.ndata[t].edges.data() if not e[2]['directed']]
		self.components['edges_d'] = self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_directed, width=[e[2]['weight'] for e in e_directed])
		self.components['edges_u'] = self.nx.draw_networkx_edges(self.ndata[t], self.pos, ax=self.axes, edgelist=e_undirected, width=[e[2]['weight'] for e in e_undirected], arrows=False)
		if self.params['agentLabel']:
			lab = None if self.params['agentLabel'] is True else {n:self.ndata[t].nodes[n]['label'] for n in self.ndata[t].nodes}
			self.components['labels'] = self.nx.draw_networkx_labels(self.ndata[t], self.pos, ax=self.axes, labels=lab, font_size=self.params['labelSize'], font_color=self.params['labelColor'], font_family=self.params['labelFamily'], font_weight=self.params['labelWeight'], alpha=self.params['labelAlpha'], horizontalalignment=self.params['labelAlign'], verticalalignment=self.params['labelVerticalAlign'])
		if self.layout=='scatter': self.axes.tick_params('both', left=True, bottom=True, labelleft=True, labelbottom=True)

		self.components['nodes'].set_picker(True)	#Listen for mouse events on nodes
		self.components['nodes'].set_pickradius(5)	#Set margin of valid events in pixels

		super().draw(t, forceUpdate)

	def rotateLayout(self):
		"""Rotate the layout among the several NetworkX layout classes, plus spatial and scatterplot layouts. This method is called when pressing 'l' with the mouse over the plot. https://helipad.dev/functions/agentsplot/rotatelayout/"""
		self.axes.set_yscale('linear') #Override default logscale keypress
		if self.params['lockLayout']: return

		#Select the next layout in the list
		layouts = ['spatial'] if self.viz.model.patches else []
		if self.scatter: layouts.append('scatter')
		if self.network in self.viz.model.agents.edges or not layouts: layouts += ['spring', 'circular', 'kamada_kawai', 'random', 'shell', 'spectral', 'spiral']
		li = layouts.index(self.layout)+1
		while li>=len(layouts): li -= len(layouts)
		self.layout = layouts[li]

		#Replace the axes object if we need to switch projections
		if self.projection == 'polar' or (self.layout=='spatial' and self.viz.model.patches and self.viz.model.patches.geometry=='polar'):
			self.projection = None if self.projection=='polar' else 'polar'
			self.viz.fig.delaxes(self.axes)
			super().launch(self.viz.fig.add_subplot(*self.subplot_position, projection=self.projection))

		#kamada_kawai requires scipy; fail silently and continue if we don't have it
		try: self.draw(self.viz.scrubval)
		except: self.rotateLayout()

	def getPatchParamValue(self, patch, t: int=None):
		"""Gather historical patch data for use in color generation. https://helipad.dev/functions/agentsplot/getpatchparamvalue/"""
		if t is not None: return patch.colorData[t]
		if patch.dead: return float('nan')
		elif 'patchProperty' not in self.params: return 0
		elif 'good:' in self.params['patchProperty']: return patch.stocks[self.params['patchProperty'].split(':')[1]]
		else: return getattr(patch, self.params['patchProperty'])

	def config(self, param: str, val=None):
		"""Sets options for the spatial plot. One argument will return the value; two arguments sets the parameter. See https://helipad.dev/functions/agentsplot/config/ for valid option names."""
		if isinstance(param, dict):
			for k,v in param.items(): self.config(k,v)
		elif val is None: return self.params[param]
		else: self.params[param] = val

#======================
# SUB-PLOT OBJECTS
# Mostly sub-plot data will use an Item object, but some need a little more
#======================

class Series(Item):
	"""Stores data on series, which link a reporter to a plot. https://helipad.dev/functions/series/"""
	@property
	def visible(self) -> bool:
		"""Whether the series is to be drawn when the plot window launches, or - if it has launched - whether the series is currently visible. https://helipad.dev/functions/series/#visible"""
		if not hasattr(self, 'line'): return self._visible
		elif hasattr(self, 'poly'): return True #If it's a stackplot
		else: return self.line.get_visible()

	@visible.setter
	def visible(self, val: bool):
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
		"""Toggles the visibility of the series. https://helipad.dev/functions/series/toggle/"""
		self.visible = not self.visible

#======================
# HELPER FUNCTIONS
#======================

def keepEvery(lst: list, n: int):
	"""Reduce the resolution of a list."""
	i,l = (1, [])
	for k in lst:
		if i%n==0: l.append(k)
		i+=1
	# if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l