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

#Used for creating an entirely new visualization window. May or may not use Matplotlib.
class BaseVisualization:
	
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

#Used for creating a synchronic plot area in the Charts visualizer. Must interface with Matplotlib and specify class.type.
#Extra kwargs in Charts.addPlot() are passed to ChartPlot.__init__().
class ChartPlot(Item):
	
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
	def scrub(self, t): pass

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
			plt.close() #Clean up after any previous runs
			plt.rcParams['figure.figsize'] = [9, 7]
		
		#fig is the figure, plots is a list of AxesSubplot objects
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(self.activePlots), sharex=True, num=title if isIpy() else None)
		if not isIpy(): self.fig.canvas.set_window_title(title)
		
		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activePlots.values(), plots): plot.axes = axes
		
		#Resize and position graph window
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
		if isIpy(): plt.show()	#Necessary for ipympl
	
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
	
	def event(self, t, color='#CC0000', linestyle='--', linewidth=1, **kwargs):
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.activePlots.values()])
		
		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.plots.values())).axes.text(t, 0, label, horizontalalignment='center')

class Charts(BaseVisualization):
	def __init__(self, model):
		self.plots = {}
		self.events = {}
		self.plotTypes = {}
		
		class BarChart(ChartPlot):
			type = 'bar'
			def __init__(self, **kwargs):
				for arg in ['horizontal', 'logscale']:
					if not arg in kwargs: kwargs[arg] = False
				super().__init__(**kwargs)
				self.bars = []
			
			def addBar(self, reporter, label, color='blue', position=None):
				bar = Item(reporter=reporter, label=label, color=color)
				
				#Add subsidiary series (e.g. percentile bars)
				bar.err = []
				if reporter in model.data.reporters and model.data.reporters[reporter].children:
					for p in model.data.reporters[reporter].children:
						if '-unsmooth' in p: continue
						bar.err.append(p)
				
				if position is None or position>=len(self.bars): self.bars.append(bar)
				else: self.bars.insert(position-1, bar)
			
			def launch(self, axes):
				super().launch(axes)
				
				cfunc, eax = (axes.barh, 'xerr') if self.horizontal else (axes.bar, 'yerr')
				kwa = {eax: [0 for bar in self.bars]} #Make sure our error bars go the right way
				rects = cfunc(range(len(self.bars)), [0 for i in self.bars], color=[bar.color for bar in self.bars], **kwa)
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
					setbar = b.element.set_width if self.horizontal else b.element.set_height
					setbar(data[b.reporter])
					b.data.append(data[b.reporter]) #Keep track
				
					if data[b.reporter] < lims[0]: lims[0] = data[b.reporter]
					if data[b.reporter] > lims[1]: lims[1] = data[b.reporter]
				
					#Update error bars
					if b.err:
						errs = [data[e] for e in b.err]
						errs.sort()
						for i,cap in enumerate(b.errPath): #Should only be 2 of these, but errs could be any length
							if len(errs) >= i+1: cap[0 if self.horizontal else 1] = errs[i]
							if errs[i] < lims[0]: lims[0] = errs[i]
							if errs[i] > lims[1]: lims[1] = errs[i]
						b.errHist.append(errs)
				
				setlim(lims)
				self.axes.autoscale_view(tight=False)
			
			def scrub(self, t):
				i = int(t/self.viz.refresh.get())-1
				for b in self.bars:
					setbar = b.element.set_width if self.horizontal else b.element.set_height
					setbar(b.data[i])
				
					if b.err: #Update error bars
						for j,cap in enumerate(b.errPath):
							if len(b.errHist[i]) >= j+1: cap[0 if self.horizontal else 1] = b.errHist[i][j]
		
		class NetworkPlot(ChartPlot):
			type = 'network'
			def __init__(self, **kwargs):
				if not 'prim' in kwargs: kwargs['prim'] = None
				if not 'kind' in kwargs: kwargs['kind'] = 'edge'
				super().__init__(**kwargs)
				self.ndata = {}
			
			def launch(self, axes):
				import networkx as nx
				self.nx = nx
				super().launch(axes)

			def update(self, data, t):
				G = self.viz.model.network(self.kind, self.prim)
				self.axes.clear()
				self.axes.set_title(self.label, fontdict={'fontsize':10})
				self.nx.draw_networkx(G, ax=self.axes)
				self.ndata[t] = G
	
			def scrub(self, t):
				self.axes.clear()
				self.axes.set_title(self.label, fontdict={'fontsize':10})
				self.nx.draw_networkx(self.ndata[t], ax=self.axes)
				
		for p in [BarChart, NetworkPlot]: self.addPlotType(p)
		model.params['updateEvery'].runtime=False
		self.refresh = model.params['updateEvery']
		self.model = model # :(
	
	@property
	def isNull(self):
		return not [chart for chart in self.plots.values() if chart.selected]
	
	@property
	def activePlots(self):
		return {k:chart for k,chart in self.plots.items() if chart.selected}
	
	def launch(self, title):
		if not len(self.activePlots): return #Windowless mode
		from matplotlib.widgets import Slider
		
		self.lastUpdate = 0
		n = len(self.activePlots)
		x = ceil(sqrt(n))
		y = ceil(n/x)
		if isIpy():
			plt.close() #Clean up after any previous runs
			plt.rcParams['figure.figsize'] = [9, 7]
		
		#fig is the figure, plots is a list of AxesSubplot objects
		self.fig, plots = plt.subplots(y, x, num=title if isIpy() else None)
		if not isIpy(): self.fig.canvas.set_window_title(title)
		
		if not isinstance(plots, ndarray): plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		if isinstance(plots[0], ndarray): plots = plots.flatten() #The x,y returns a 2D array
		for plot, axes in zip(self.activePlots.values(), plots): plot.launch(axes)
		
		#Position graph window
		fm = plt.get_current_fig_manager()
		if hasattr(fm, 'window'):
			x_px = fm.window.winfo_screenwidth()*2/3
			if x_px + 400 > fm.window.winfo_screenwidth(): x_px = fm.window.winfo_screenwidth()-400
			self.fig.set_size_inches(x_px/self.fig.dpi, fm.window.winfo_screenheight()/self.fig.dpi)
			fm.window.wm_geometry("+400+0")
		
		#Time slider
		ref = self.refresh.get()
		plt.subplots_adjust(bottom=0.12) #Make room for the slider
		sax = plt.axes([0.1,0.01,.75,0.03], facecolor='#EEF')
		self.timeslider = Slider(sax, 't=', 0, ref, ref, valstep=ref, closedmin=False)
		self.timeslider.on_changed(self.scrub)
		
		plt.draw()
		if isIpy(): plt.show()	#Necessary for ipympl
	
	def update(self, data):
		data = {k:v[-1] for k,v in data.items()}
		t = self.model.t #cheating?
		for c in self.activePlots.values(): c.update(data, t)
		
		#Update slider
		self.timeslider.valmax = t
		self.timeslider.set_val(t)
		self.timeslider.ax.set_xlim(0,t) #Refresh
		
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')
		plt.pause(0.0001)
	
	#Update the graph to a particular model time
	def scrub(self, t):
		for c in self.activePlots.values(): c.scrub(t)
		self.fig.patch.set_facecolor(self.events[t] if t in self.events else 'white')
	
	def addPlot(self, name, label, **kwargs):
		if not 'type' in kwargs: kwargs['type'] = 'bar'
		if not kwargs['type'] in self.plotTypes: raise KeyError('\''+kwargs['type']+'\' is not a registered plot visualizer.')
		self.plots[name] = self.plotTypes[kwargs['type']](name=name, label=label, selected=True, viz=self, **kwargs)
		return self.plots[name]
	
	def addPlotType(self, clss):
		if not issubclass(clss, ChartPlot): raise TypeError('New plot types must subclass ChartPlot.')
		self.plotTypes[clss.type] = clss
	
	def event(self, t, color='#FDC', **kwargs):
		ref = self.refresh.get()
		self.events[ceil(t/ref)*ref] = color
	
def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l