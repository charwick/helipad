# ==========
# The matplotlib interface for plotting
# Do not run this file; import model.py and run from your file.
# ==========

from numpy import ndarray, asanyarray, log10
import matplotlib.pyplot as plt, matplotlib.style as mlpstyle
from helipad.helpers import *
mlpstyle.use('fast')

class Graph:
	#listOfPlots is the trimmed model.plots list
	def __init__(self, listOfPlots, **kwargs):
		#fig is the figure, plots is a list of AxesSubplot objects
		self.lastUpdate = 0
		self.resolution = 1
		if isIpy():
			plt.ioff() #Can't re-launch plots without manually closing otherwise
			plt.rcParams['figure.figsize'] = [12, 8]
		
		#The Tkinter way of setting the title doesn't work in Jupyter
		#The Jupyter way works in Tkinter, but also serves as the figure id, so new graphs draw on top of old ones
		self.fig, plots = plt.subplots(len(listOfPlots), sharex=True, num=kwargs['title'] if isIpy() else None)
		if not isIpy(): self.fig.canvas.set_window_title(kwargs['title'])
		
		if not isinstance(plots, ndarray):
			plots = asanyarray([plots]) #.subplots() tries to be clever & returns a different data type if len(plots)==1
		for plot, axes in zip(listOfPlots.values(), plots):
			plot.axes = axes
		self.plots = listOfPlots
		
		#Position graph window
		fm = plt.get_current_fig_manager()
		if hasattr(fm, 'window'):
			x_px = fm.window.winfo_screenwidth()*2/3
			if x_px + 400 > fm.window.winfo_screenwidth(): x_px = fm.window.winfo_screenwidth()-400
			self.fig.set_size_inches(x_px/self.fig.dpi, fm.window.winfo_screenheight()/self.fig.dpi)
			fm.window.wm_geometry("+400+0")
		
		#Cycle over plots
		for pname, plot in self.plots.items():
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
	
	#data is the *incremental* data
	def update(self, data):
		newlen = len(next(data[x] for x in data))*self.resolution #Length of the data times the resolution
		time = newlen + len(next(iter(self.plots.values())).series[0].fdata)*self.resolution
		
		#Append new data to cumulative series
		for plot in self.plots.values():
			for serie in plot.series:
				if callable(serie.reporter):						#Lambda functions
					for i in range(int(newlen/self.resolution)):
						serie.fdata.append(serie.reporter(time-newlen+(1+i)*self.resolution))
				elif serie.reporter in data: serie.fdata += data[serie.reporter] #Actual data
				else: continue									#No data
		
		#Redo resolution at 2500, 25000, etc
		if 10**(log10(time/2.5)-3) >= self.resolution:
			self.resolution *= 10
			for plot in self.plots.values():
				for serie in plot.series:
					serie.fdata = keepEvery(serie.fdata, 10)
		
		#Update the actual graphs. Has to be after the new resolution is set
		tseries = range(0, time, self.resolution)
		for plot in self.plots.values():
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
		# for g in self.plots:
		# 	if c1.series in g.get_lines():
		# 		g.relim()
		# 		g.autoscale_view(tight=True)
		
		self.fig.canvas.draw()

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

def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l