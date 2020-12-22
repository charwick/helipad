# ==========
# The matplotlib interface for plotting
# Do not run this file; import model.py and run from your file.
# ==========

from numpy import ndarray, asanyarray, log10
import matplotlib.pyplot as plt, matplotlib.style as mlpstyle
from helipad.helpers import *
mlpstyle.use('fast')

class TimeSeries:
	def __init__(self, model):
		self.hasWindow = False
		self.selector = model.addParameter('plots', 'Plots', 'checkgrid', [], opts={}, runtime=False, config=True)
		self.model = model #Unhappy with this
		
		#Plot categories
		self.plots = {}
		plotList = {
			'demand': 'Demand',
			'shortage': 'Shortages',
			'money': 'Money',
			'utility': 'Utility'
		}
		for name, label in plotList.items(): self.addPlot(name, label, selected=False)
		
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
	
	def canLaunch(self, model):
		if not [plot for plot in self.plots.values() if plot.selected] and (not model.param('stopafter') or not model.param('csv')):
			warnings.warn('Plotless mode requires stop period and CSV export to be enabled.', None, 3)
			return False
		else: return True
	
	@property
	def activePlots(self):
		return {k:plot for k,plot in self.plots.items() if plot.selected}
	
	#listOfPlots is the trimmed model.plots list
	def launch(self, title, **kwargs):
		if not len(self.activePlots): return #Windowless mode
		
		#fig is the figure, plots is a list of AxesSubplot objects
		self.lastUpdate = 0
		self.resolution = 1
		self.verticals = []
		if isIpy():
			plt.ioff() #Can't re-launch plots without manually closing otherwise
			plt.rcParams['figure.figsize'] = [12, 8]
		
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(self.activePlots), sharex=True, num=title if isIpy() else None)
		if not isIpy(): self.fig.canvas.set_window_title(title)
		
		if not isinstance(plots, ndarray):
			plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(self.activePlots.values(), plots):
			plot.axes = axes
		
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
		
		self.hasWindow = True
		plt.draw()
	
	#Called from model.terminate()
	def terminate(self, model):
		if not self.hasWindow:
			for p in ['stopafter', 'csv']: model.params[p].enable()
		self.hasWindow = False
	
	#data is the *incremental* data
	def update(self, data):
		newlen = len(next(data[x] for x in data))*self.resolution #Length of the data times the resolution
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
		if getattr(self.model, 'cpanel', False):
			if isIpy(): self.model.cpanel.invalidate()
			else: raise RuntimeError('Cannot add plots after control panel is drawn')
		plot = Plot(model=self.model, name=name, label=label, series=[], logscale=logscale, stack=stack, selected=selected)
		if position is None or position > len(self.plots):
			self.selector.opts[name] = label
			self.plots[name] = plot
		else:		#Reconstruct the dicts because there's no insert method…
			newopts, newplots, i = ({}, {}, 1)
			for k,v in self.selector.opts.items():
				if position==i:
					newopts[name] = label
					newplots[name] = plot
				newopts[k] = v
				newplots[k] = self.plots[k]
				i+=1
			self.selector.opts = newopts
			self.plots = newplots
		
		self.selector.vars[name] = selected
		if selected: self.selector.default.append(name)
		if getattr(self.model, 'cpanel', False) and not self.cpanel.valid: self.model.cpanel.__init__(self.model, redraw=True) #Redraw if necessary
		
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
		self.verticals.append([p.axes.axvline(x=t, color=color, linestyle=linestyle, linewidth=linewidth) for p in self.plots.values()])
		
		# Problem: Need x to be in plot coordinates but y to be absolute w.r.t the figure
		# next(iter(self.plots.values())).axes.text(t, 0, label, horizontalalignment='center')

class Plot(Item):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
	
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

def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l