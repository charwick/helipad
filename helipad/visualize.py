# ==========
# The matplotlib interface for plotting
# Do not run this file; import model.py and run from your file.
# ==========

from numpy import ndarray, asanyarray, log10
from math import sqrt, ceil
import matplotlib.pyplot as plt, matplotlib.style as mlpstyle
from abc import ABC, abstractmethod
from helipad.helpers import *
mlpstyle.use('fast')

class BaseVisualization:
	
	#Create the window. Mandatory to implement
	@abstractmethod
	def launch(self, title): pass
	
	#Refresh every so many periods. Mandatory to implement
	#data is the *incremental* data
	@abstractmethod
	def update(self, data): pass
	
	#Called from model.terminate(). Optional to implement
	def terminate(self, model): pass

class TimeSeries(BaseVisualization):
	def __init__(self, model):
		self.selector = model.addParameter('plots', 'Plots', 'checkgrid', [], opts={}, runtime=False, config=True)
		self.model = model #Unhappy with this
		
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

				#Check against columns and not reporters so percentiles work
				if not callable(reporter) and not reporter in self.model.data.all:
					raise KeyError('Reporter \''+reporter+'\' does not exist. Be sure to register reporters before adding series.')
		
				#Add subsidiary series (e.g. percentile bars)
				subseries = []
				if reporter in self.model.data.reporters and isinstance(self.model.data.reporters[reporter].func, tuple):
					for p, f in self.model.data.reporters[reporter].func[1].items():
						subkey = reporter+'-'+str(p)+'-pctile'
						subseries.append(self.addSeries(subkey, '', color.lighten(), style='--'))

				#Since many series are added at setup time, we have to de-dupe
				for s in self.series:
					if s.reporter == reporter:
						self.series.remove(s)
		
				series = Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=self.name)
				self.series.append(series)
				if reporter in self.model.data.reporters: self.model.data.reporters[reporter].series.append(series)
				return series
		self.plotclass = Plot
		
		#Plot categories
		self.plots = {}
		self.addPlot('utility', 'Utility', selected=False)
		
		if len(model.goods) >= 2:
			self.addPlot('demand', 'Demand', selected=False)
			self.addPlot('shortage', 'Shortages', selected=False)
		if model.moneyGood is not None:
			self.addPlot('money', 'Money', selected=False)
		
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
	
	@property
	def isNull(self):
		return not [plot for plot in self.plots.values() if plot.selected]
	
	@property
	def activePlots(self):
		return {k:plot for k,plot in self.plots.items() if plot.selected}
	
	#listOfPlots is the trimmed model.plots list
	def launch(self, title):
		if not len(self.activePlots): return #Windowless mode
		
		self.lastUpdate = 0
		self.resolution = 1
		self.verticals = []
		if isIpy():
			plt.ioff() #Can't re-launch plots without manually closing otherwise
			plt.rcParams['figure.figsize'] = [12, 8]
		
		#fig is the figure, plots is a list of AxesSubplot objects
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(self.activePlots), sharex=True, num=title if isIpy() else None)
		if not isIpy(): self.fig.canvas.set_window_title(title)
		
		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activePlots.values(), plots): plot.axes = axes
		
		#Position graph window
		fm = plt.get_current_fig_manager()
		if hasattr(fm, 'window'):
			x_px = fm.window.winfo_screenwidth()*2/3
			if x_px + 400 > fm.window.winfo_screenwidth(): x_px = fm.window.winfo_screenwidth()-400
			self.fig.set_size_inches(x_px/self.fig.dpi, fm.window.winfo_screenheight()/self.fig.dpi)
			fm.window.wm_geometry("+400+0")
		
		#Cycle over plots
		for pname, plot in self.activePlots.items():
			plot.axes.margins(x=0)
			if plot.stack:
				lines = plot.axes.stackplot([], *[[] for s in plot.series], color=[s.color.hex for s in plot.series])
				for series, poly in zip(plot.series, lines): series.poly = poly
				plot.axes.margins(y=0)
			
			if plot.logscale:
				plot.axes.set_yscale('log')
				plot.axes.set_ylim(1/2, 2, auto=True)
				
			#Create a line for each series
			#Do this even for stackplots because the line object is necessary to create the legend
			for series in plot.series:
				series.line, = plot.axes.plot([], label=series.label, color=series.color.hex, linestyle=series.style)
				series.fdata = []
				series.line.subseries = series.subseries
				series.line.label = series.label
			
			#Set up the legend for click events on both the line and the legend
			leg = plot.axes.legend(loc='upper right')
			for legline, label in zip(leg.get_lines(), leg.get_texts()):
				legline.set_picker(True)	#Listen for mouse events on the legend line
				legline.set_pickradius(5)	#Set margin of valid events in pixels
				label.set_picker(5)			#Do both on the legend text
				for s in plot.series:
					if s.label==label.get_text():
						label.series = s.line
						legline.series = s.line
						legline.otherComponent = label
						label.otherComponent = legline
						break
		
		#Style graphs
		self.fig.tight_layout()
		self.fig.subplots_adjust(hspace=0, bottom=0.05, right=1, top=0.97, left=0.1)
		# plt.setp([a.get_xticklabels() for a in self.fig.axes[:-1]], visible=False)	#What was this for again…?
		self.fig.canvas.mpl_connect('pick_event', self.toggleLine)
		
		plt.draw()
	
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
		
		if self.resolution > self.model.param('updateEvery'): self.model.param('updateEvery', self.resolution)
		if isIpy(): self.fig.canvas.draw()
		plt.pause(0.0001)
	
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
		plot = self.plotclass(model=self.model, name=name, label=label, series=[], logscale=logscale, stack=stack)
		
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
	
	def addVertical(self, t, color, linestyle, linewidth):
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.activePlots.values()])
		
		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.plots.values())).axes.text(t, 0, label, horizontalalignment='center')

class Charts(BaseVisualization):
	def __init__(self, model):
		self.charts = {}
		
		class Chart(Item):
			def __init__(self, **kwargs):
				super().__init__(**kwargs)
				self.bars = []
			
			def addBar(self, reporter, label, color='blue', error=None, position=None):
				bar = Item(reporter=reporter, label=label, color=color, error=error)
				if position is None or position>=len(self.bars): self.bars.append(bar)
				else: self.bars.insert(position-1, bar)
				
		self.chartclass = Chart
	
	@property
	def isNull(self):
		return not [chart for chart in self.charts.values() if chart.selected]
	
	@property
	def activeCharts(self):
		return {k:chart for k,chart in self.charts.items() if chart.selected}
	
	def launch(self, title):
		if not len(self.activeCharts): return #Windowless mode
		
		self.lastUpdate = 0
		n = len(self.activeCharts)
		x = ceil(sqrt(n))
		y = ceil(n/x)
		
		#fig is the figure, plots is a list of AxesSubplot objects
		self.fig, plots = plt.subplots(y, x, num=title if isIpy() else None, constrained_layout=True)
		if not isIpy(): self.fig.canvas.set_window_title(title)
		
		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activeCharts.values(), plots): plot.axes = axes
		
		#Cycle over charts
		for cname, chart in self.activeCharts.items():
			cfunc = chart.axes.barh if chart.horizontal else chart.axes.bar
			rects = cfunc(range(len(chart.bars)), [0 for i in range(len(chart.bars))], color=[bar.color for bar in chart.bars])
			for bar, rect in zip(chart.bars, rects): bar.rect = rect
			
			cxfunc = chart.axes.set_yticklabels if chart.horizontal else chart.axes.set_xticklabels
			cxfunc([bar.label for bar in chart.bars])
			chart.axes.margins(x=0)
			chart.axes.set_title(chart.label)
			
			if chart.logscale:
				if chart.horizontal:
					chart.axes.set_xscale('log')
					chart.axes.set_xlim(1/2, 2, auto=True)
				else:
					chart.axes.set_yscale('log')
					chart.axes.set_ylim(1/2, 2, auto=True)
		
		plt.draw()
	
	def update(self, data):
		data = {k:v[-1] for k,v in data.items()}
		for c in self.activeCharts.values():
			for b in c.bars:
				bfunc = b.rect.set_width if c.horizontal else b.rect.set_height
				bfunc(data[b.reporter])
			c.axes.relim()
			c.axes.autoscale_view(tight=False)
		
		plt.pause(0.0001)
	
	def addChart(self, name, label, logscale=False, horizontal=False):
		self.charts[name] = self.chartclass(name=name, label=label, selected=True, logscale=logscale, horizontal=horizontal)
		return self.charts[name]
	
def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l