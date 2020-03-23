# ==========
# The control panel and plot interfaces
# Do not run this file; import model.py and run from your file.
# ==========

from tkinter import *
from tkinter.ttk import Progressbar
from colour import Color
from itertools import combinations
from numpy import ndarray, asanyarray, log10
from math import ceil
# import time #For performance testing
import importlib, string, random as rand2
import matplotlib.pyplot as plt
import matplotlib.style as mlpstyle
mlpstyle.use('fast')
if importlib.util.find_spec('Pmw') is not None:
	import Pmw
	hasPmw = True
else:
	print('Use pip to install Pmw in order to use tooltips')
	hasPmw = False

class GUI():
	running = False
	sliders = {}
	
	def __init__(self, parent, model, headless=False):
		self.parent = parent
		self.model = model
		self.lastUpdate = None
		self.balloon = Pmw.Balloon(parent) if hasPmw else None
		self.updateEvery = 20
		self.checks = {} #Shock checkboxes
		self.headless = headless
		
		bgcolors = ('#FFFFFF','#EEEEEE')
		fnum = 1
		
		#
		# CALLBACK FUNCTION GENERATORS FOR TKINTER ELEMENTS
		#
		def menuCallback(fullvar, callback=None):
			def cb(val=None):
				if '-' in fullvar:
					obj, var, item = fullvar.split('-')	#Per-object variables
					if '_' in obj:
						obj, prim = obj.split('_')
						val = getattr(self.model, obj+'Param')(var, item, prim=prim)
					else: val = getattr(self.model, obj+'Param')(var, item)
				else:
					var = fullvar
					val = self.model.param(var)
				
				if callable(callback): callback(self.model, var, val)
			return cb
		
		def setVar(vname):
			def sv(val=None):
			
				#The checkbox callback doesn't pass the argument, so we've got to get the value the hard way
				#But we also know it's a boolean if we don't get it
				#Otherwise it came from a slider, which passes a string that ought to be a float
				if val is None: val = self.sliders[vname].variable.get()
				else: val = float(val)
			
				self.model.updateVar(vname, val)
			return sv
		
		#For shock buttons.
		#Can't do an inline lambda here because lambdas apparently don't preserve variable context
		def shockCallback(name):
			return lambda: self.model.shocks.do(name)
		
		#Toggle the progress bar between determinate and indeterminate when stopafter gets changed
		def switchPbar(val):
			if not val:
				self.progress.config(mode='indeterminate')
				if self.running: self.progress.start()
			else:
				self.progress.config(mode='determinate')
				if self.running: self.progress.stop()
			self.model.root.update()
		
		#
		# CONSTRUCT CONTROL PANEL INTERFACE
		#
			
		
		#Put this up here so the variable name is accessible when headless
		frame1 = Frame(self.parent, padx=10, pady=10, bg=bgcolors[fnum%2])
		self.stopafter = checkEntry(frame1, title='Stop on period', bg=bgcolors[fnum%2], default=10000, width=10, type='int', callback=switchPbar)
		
		if headless: return
		font = ('Lucida Grande', 16) if sys.platform=='darwin' else ('Calibri', 14)
		
		self.stopafter.grid(row=0,column=0, columnspan=3)
		
		#CSV export
		self.expCSV = checkEntry(frame1, title='CSV?', bg=bgcolors[fnum%2], default='Filename')
		self.expCSV.grid(row=1, column=0, columnspan=3)
		
		self.refresh = logSlider(frame1, title="Refresh every __ periods", orient=HORIZONTAL, values=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], bg=bgcolors[fnum%2], length=150, command=lambda val: setattr(self, 'updateEvery', int(val)))
		self.refresh.slide.set(4) #Default refresh of 20
		self.refresh.grid(row=2, column=0, columnspan=2, pady=(10,0))
		self.runButton = Button(frame1, text='Run', command=self.preparePlots, padx=10, pady=10, highlightbackground=bgcolors[fnum%2])
		self.runButton.grid(row=2, column=2, pady=(15,0))
		
		#Buttons
		b=0
		for f in self.model.buttons:
			button = Button(frame1, text=f[0], command=f[1], padx=10, pady=10)
			button.grid(row=4, column=b%2, pady=(15,0))
			if hasPmw and f[2] is not None: self.balloon.bind(button, f[2])
			b+=1
		
		frame1.columnconfigure(0,weight=1)
		frame1.columnconfigure(1,weight=1)
		frame1.pack(fill="x", side=TOP)
		fnum += 1
		
		#Can't change the background color of a progress bar on Mac, so we have to put a gray stripe on top :-/
		frame0 = Frame(self.parent, padx=10, pady=0, bg=bgcolors[1])
		self.progress = Progressbar(frame0, length=250, style="whitebg.Horizontal.TProgressbar")
		self.progress.grid(row=0, column=0)
		frame0.columnconfigure(0,weight=1)
		frame0.pack(fill="x", side=TOP)
		
		#Item parameter sliders
		def buildSlider(itemDict, paramDict, setget, obj, prim=None, fnum=fnum):
			for k, var in paramDict.items():
				bpf_super = expandableFrame(bg=bgcolors[fnum%2], padx=5, pady=10, text=var[1]['title'], fg="#333", font=font)
				bpf = bpf_super.subframe
				
				i=0
				for name, b in itemDict.items():
					bname = obj+'-'+k+'-'+name
					
					#Circle for item color
					lframe = Frame(bpf, bg=bgcolors[fnum%2], padx=0, pady=0)
					c = Canvas(lframe, width=17, height=12, bg=bgcolors[fnum%2], highlightthickness=0)
					c.create_oval(0,0,12,12,fill=b.color.hex_l, outline='')
					c.grid(row=0, column=0, pady=(0,8))
					
					#Item name label
					if var[1]['type'] != 'check':
						Label(lframe, text=name.title(), fg="#333", bg=bgcolors[fnum%2]).grid(row=0, column=1, pady=(0,8))
				
						if var[1]['type'] == 'menu':
							self.sliders[bname] = OptionMenu(bpf, paramDict[k][0][name], command=menuCallback(bname, var[1]['callback']), *var[1]['opts'].values())
							self.sliders[bname].config(bg=bgcolors[fnum%2])
						elif var[1]['type'] == 'slider':
							self.sliders[bname] = Scale(bpf, from_=var[1]['opts']['low'], to=var[1]['opts']['high'], resolution=var[1]['opts']['step'], orient=HORIZONTAL, length=150, highlightthickness=0, command=setVar(bname), bg=bgcolors[fnum%2])
							self.sliders[bname].set(setget(k, name, prim=prim))
						
						self.sliders[bname].grid(row=ceil((i+1)/2)*2-1, column=i%2)
					
					#Do everything differently if we've got a checkbox
					else:
						self.sliders[bname] = Checkbutton(lframe, text=name.title(), var=paramDict[k][0][name], onvalue=True, offvalue=False, command=setVar(bname), bg=bgcolors[fnum%2])
						self.sliders[bname].variable = paramDict[k][0][name] #Keep track of this because it doesn't pass the value to the callback
						self.sliders[bname].grid(row=0, column=1)
					
					bpf.columnconfigure(0,weight=1)
					bpf.columnconfigure(1,weight=1)
					lframe.grid(row=ceil((i+1)/2)*2, column=i%2)
					if hasPmw and var[1]['desc'] is not None: self.balloon.bind(self.sliders[bname], var[1]['desc'])
					
					i+=1
				bpf_super.pack(fill="x", side=TOP)
				
		buildSlider(model.nonMoneyGoods, model.goodParams, model.goodParam, 'good', fnum=fnum)
		if model.goodParams != {}: fnum += 1 #Only increment the stripe counter if we had any good params to draw
		for p,v in model.primitives.items():
			if v['breedParams'] != {}:
				buildSlider(v['breeds'], v['breedParams'], model.breedParam, 'breed_'+p, prim=p, fnum=fnum)
				fnum += 1
		
		#Parameter sliders
		for k, var in self.model.params.items():
			var = var[1]
			if var['type'] == 'hidden': continue
			elif var['type'] == 'check':
				f = Frame(self.parent, bg=bgcolors[fnum%2], pady=5)
				self.sliders[k] = Checkbutton(f, text=var['title'], var=self.model.params[k][0], onvalue=True, offvalue=False, command=setVar(k), bg=bgcolors[fnum%2])
				self.sliders[k].variable = self.model.params[k][0] #Keep track of this because it doesn't pass the value to the callback
				self.sliders[k].pack()
			else:
				f = Frame(self.parent, bg=bgcolors[fnum%2], padx=10, pady=8)
				Label(f, text=var['title'], fg="#333", bg=bgcolors[fnum%2]).pack(side=LEFT, padx=8, pady=3)
				if var['type'] == 'menu':
					#Callback is different because menus automatically update their variable
					self.sliders[k] = OptionMenu(f, self.model.params[k][0], *var['opts'].values(), command=menuCallback(k, var['callback']))
					self.sliders[k].config(bg=bgcolors[fnum%2])
				elif var['type'] == 'slider':
					self.sliders[k] = Scale(f, from_=var['opts']['low'], to=var['opts']['high'], resolution=var['opts']['step'], orient=HORIZONTAL, length=150, highlightthickness=0, command=setVar(k), bg=bgcolors[fnum%2])
					self.sliders[k].set(var['dflt'])
					
				self.sliders[k].pack(side=RIGHT)
				if hasPmw and var['desc'] is not None: self.balloon.bind(self.sliders[k], var['desc'])
				
			f.pack(fill="x", side=TOP)
		fnum += 1
		
		# Graph Checkboxes
		frame7 = expandableFrame(self.parent, text='Plots', padx=5, pady=8, font=font, bg=bgcolors[fnum%2])
		i=0
		for k, v in self.model.plots.items():
			i += 1
			self.checks[k] = textCheck(frame7.subframe, text=v.label, anchor='w', defaultValue=k in self.model.defaultPlots, bg=(bgcolors[fnum%2],'#419BF9'))
			self.checks[k].grid(row=int(ceil(i/3)), column=(i-1)%3, sticky='WE')

		frame7.subframe.columnconfigure(0,weight=1)
		frame7.subframe.columnconfigure(1,weight=1)
		frame7.subframe.columnconfigure(2,weight=1)
		frame7.pack(fill="x", side=TOP)
		
		#Shock checkboxes
		if self.model.shocks.number > 0:
			fnum += 1
			frame8 = expandableFrame(self.parent, text='Shocks', padx=5, pady=8, font=font, bg=bgcolors[fnum%2])
			for shock in self.model.shocks.shocks.values():
				if callable(shock['timerFunc']):
					shock['guiElement'] = Checkbutton(frame8.subframe, text=shock['name'], var=shock['active'], onvalue=True, offvalue=False, bg=bgcolors[fnum%2], anchor=W)
				elif shock['timerFunc'] == 'button':
					shock['guiElement'] = Button(frame8.subframe, text=shock['name'], command=shockCallback(shock['name']), padx=10, pady=10)
				
				if hasPmw and shock['desc'] is not None:
					self.balloon.bind(shock['guiElement'], shock['desc'])
				shock['guiElement'].pack(fill=BOTH)
			frame8.pack(fill="x", side=TOP)
		
		#Set application name
		if sys.platform=='darwin':
			if importlib.util.find_spec("Foundation") is not None:
				from Foundation import NSBundle
				bundle = NSBundle.mainBundle()
				if bundle:
					info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
					if info and info['CFBundleName'] == 'Python':
						info['CFBundleName'] = 'Helipad'
			else: print('Use pip to install pyobjc for nice Mac features')
		
		#Passes itself to the callback
		self.model.doHooks('GUIPostInit', [self])
	
	#Start a new model
	def preparePlots(self):
		self.model.setup()
		
		#Trim the plot list to the checked items and sent it to Graph
		if self.headless: plotsToDraw = {k: self.model.plots[k] for k in self.model.defaultPlots}
		else: plotsToDraw = {k: self.model.plots[k] for k, i in self.checks.items() if i.enabled and i.get()}
		
		#If there are any graphs to plot
		if not len(plotsToDraw.items()) and (not self.stopafter.get() or not self.expCSV.get()):
			print('Plotless mode requires stop period and CSV export to be enabled.')
			return
		
		#Disable graph checkboxes and any parameters that can't be changed during runtime
		for c in self.checks: self.checks[c].disable()
		for k, var in self.model.params.items():
			if not var[1]['runtime'] and k in self.sliders:
				self.sliders[k].configure(state='disabled')
		
		#If we've got plots, instantiate the Graph object
		if len(plotsToDraw.items()) > 0:
			def catchKeypress(event):
				#Toggle legend boxes
				if event.key == 't':
					for g in self.graph.graph:
						leg = g.get_legend()
						leg.set_visible(not leg.get_visible())
					self.graph.fig.canvas.draw()
			
				#Pause on spacebar
				elif event.key == ' ':
					if self.running: self.pause()
					else: self.run()
			
				#User functions
				self.model.doHooks('graphKeypress', [event.key, self])
		
			self.graph = Graph(plotsToDraw)
			self.graph.fig.canvas.mpl_connect('close_event', self.terminate)
			self.graph.fig.canvas.mpl_connect('key_press_event', catchKeypress)
		
		#Otherwise don't allow stopafter to be disabled or we won't have any way to stop the model
		else:
			self.graph = None
			self.stopafter.disable()
			self.expCSV.disable()
		
		self.lastUpdate = 0
		self.run()
	
	#Resume a model
	def run(self):
		self.running = True
		if hasattr(self, 'runButton'):
			self.runButton['text'] = 'Pause'
			self.runButton['command'] = self.pause
		
		if not self.stopafter.get():
			self.progress.config(mode='indeterminate')
			self.progress.start()
		else:
			self.progress.config(mode='determinate')
		
		# start = time.time()
		while self.running:
			for t in range(self.updateEvery):
				self.model.step()
	
			#Update graphs
			if self.graph is not None:
				data = self.model.data.getLast(self.model.t - self.lastUpdate)
		
				if (self.graph.resolution > 1):
					data = {k: keepEvery(v, self.graph.resolution) for k,v in data.items()}
				self.graph.update(data)
				self.lastUpdate = self.model.t
				if self.graph.resolution > self.updateEvery: self.updateEvery = self.graph.resolution
			
			## Performance indicator
			# newtime = time.time()
			# print('Period', self.model.t, 'at', self.updateEvery/(newtime-start), 'periods/second')
			# start = newtime
		
			st = self.stopafter.get()
			if st:
				self.progress['value'] = self.model.t/st*100
				if self.graph is None: self.model.root.update() #Make sure we don't hang the interface if plotless
				if self.model.t>=st: self.terminate()
		
		remainder = self.model.t % self.updateEvery
		if remainder > 0: self.graph.update(self.model.data.getLast(remainder)) #Last update at the end
	
	#Step one period at a time and update the graph
	#For use in debugging
	def step(self):
		t = self.model.step()
		self.graph.update(self.model.data.getLast(1))
		return t
	
	def pause(self):
		self.running = False
		self.progress.stop()
		self.runButton['text'] = 'Run'
		self.runButton['command'] = self.run
		self.model.doHooks('pause', [self])
	
	def terminate(self, evt=False):
		if self.running and (self.headless or self.expCSV.get()):
			self.model.data.saveCSV(self.expCSV.get() if not self.headless else 'data')
		
		self.running = False
		self.model.hasModel = False
		self.progress.stop()
		
		#Re-enable checkmarks and options
		for c in self.checks.values(): c.enable()
		for s in self.sliders.values(): s.configure(state='normal')
		self.stopafter.enable()
		self.expCSV.enable()
		
		#Passes GUI object to the callback
		self.model.doHooks('terminate', [self])
		
		if hasattr(self, 'runButton'):
			self.runButton['text'] = 'New Model'
			self.runButton['command'] = self.preparePlots

class Graph():
	#listOfPlots is the trimmed model.plots list
	def __init__(self, listOfPlots):
		#fig is the figure, graph is a list of AxesSubplot objects
		# plt.clf()
		self.resolution = 1
		self.fig, self.graph = plt.subplots(len(listOfPlots), sharex=True)
		
		#Position graph window
		window = plt.get_current_fig_manager().window
		x_px = window.winfo_screenwidth()*2/3
		if x_px + 400 > window.winfo_screenwidth(): x_px = window.winfo_screenwidth()-400
		self.fig.set_size_inches(x_px/self.fig.dpi, window.winfo_screenheight()/self.fig.dpi)
		window.wm_geometry("+400+0")
		
		if not isinstance(self.graph, ndarray):
			self.graph = asanyarray([self.graph]) #.subplots() tries to be clever & returns a different data type if len(self.graph)==1
		
		#Cycle over plots
		self.series, i = {}, 0
		for pname, plot in listOfPlots.items():
			if plot.logscale:
				self.graph[i].set_yscale('log')
				self.graph[i].set_ylim(1/2, 2, auto=True)
				
			#Cycle over series
			#serobj is our line object
			for series in plot.series:
				serobj, = self.graph[i].plot([], label=series.label, color='#'+series.color, linestyle=series.style)
				serobj.fdata = []
				serobj.subseries = series.subseries
				serobj.label = series.label
				
				#If it's a lambda function, save it for later and create a place to put its output
				if callable(series.reporter):
					serobj.func = series.reporter
					key = randomword(10)
				else: key = series.reporter
				self.series[key] = serobj
			
			#Set up the legend for click events on both the line and the legend
			leg = self.graph[i].legend(loc='upper right')
			j = 0
			for legline, label in zip(leg.get_lines(), leg.get_texts()):
				legline.set_picker(5)
				label.set_picker(5)
				for s in self.series.values():
					if s.label==label.get_text():
						label.series = s
						legline.series = s
						legline.otherComponent = label
						label.otherComponent = legline
						break
				j+=1
			i+=1
		
		#Style graphs
		self.fig.tight_layout()
		self.fig.subplots_adjust(hspace=0, bottom=0.05, right=1, top=0.97, left=0.1)
		# plt.setp([a.get_xticklabels() for a in self.fig.axes[:-1]], visible=False)	#What was this for again…?
		self.fig.canvas.mpl_connect('pick_event', self.toggleLine)
		
		plt.draw()
		# plt.ion()	# Makes plt.draw() unnecessary, but also closes the window after it's done
	
	#data is the *incremental* data
	def update(self, data):
		newlen = len(next(data[x] for x in data))*self.resolution #Length of the data times the resolution
		time = newlen + len(next(self.series[x] for x in self.series).fdata)*self.resolution
		
		for k, serie in self.series.items():
			if hasattr(serie,'func'):						#Lambda functions
				for i in range(int(newlen/self.resolution)):
					serie.fdata.append(serie.func(time-newlen+(1+i)*self.resolution))
			elif k in data: serie.fdata += data[k]			#Actual data
			else: continue									#No data
		
		if 10**(log10(time/2.5)-3) >= self.resolution:		#Redo resolution at 2500, 25000, etc
			self.resolution *= 10
			for k, serie in self.series.items():
				serie.fdata = keepEvery(serie.fdata, 10)
		
		#Has to be after the new resolution is set
		tseries = range(0, time, self.resolution)
		for k, serie in self.series.items():
			serie.set_ydata(serie.fdata)
			serie.set_xdata(tseries)

		for g in self.graph:	#g is an Axes object
			g.relim()
			g.autoscale_view(tight=False)
			ylim = g.get_ylim()
			
			#Prevent decaying averages on logscale graphs from compressing the entire view
			if g.get_yscale() == 'log' and ylim[0] < 10**-6: g.set_ylim(bottom=10**-6)

		plt.pause(0.0001)
	
	def toggleLine(self, event):
		c1 = event.artist			#The label or line that was clicked
		vis = not c1.series.get_visible()
		c1.series.set_visible(vis)
		for s in c1.series.subseries: self.series[s].set_visible(vis) #Toggle subseries (e.g. percentile bars)
		c1.set_alpha(1.0 if vis else 0.2)
		c1.otherComponent.set_alpha(1.0 if vis else 0.2)

		## Won't work because autoscale_view also includes hidden lines
		## Will have to actually remove and reinstate the line for this to work
		# for g in self.graph:
		# 	if c1.series in g.get_lines():
		# 		g.relim()
		# 		g.autoscale_view(tight=True)
		
		self.fig.canvas.draw()

def keepEvery(lst, n):
	i,l = (1, [])
	for k in lst:
		if (i%n==0): l.append(k)
		i+=1
	if len(lst)%n != 0: print('Original:',len(lst),'New:',len(l),'Remainder:',len(lst)%n)
	return l
#
# MISCELLANEOUS INTERFACE ELEMENTS
#

# A slider with defined non-linear intervals
class logSlider(Frame):	
	def __init__(self, parent=None, title=None, command=None,
		bg='#FFFFFF', font=('Lucida Grande',12),
		values=(), **kwargs
	):
		Frame.__init__(self, parent, bg=bg)
		if title: Label(self, font=font, text=title, bg=bg).pack(side=TOP)
		self.values = values
		
		self.extCommand = command
		self.number = 0
		
		#Callback function
		def setValue(val):
			self.number = self.values[int(val)]
			self.text.configure(text=self.number)
			if self.extCommand != None: self.extCommand(self.values[int(val)])
		
		self.slide = Scale(self, command=setValue,
			bg=bg, showvalue=0, from_=0, to=len(self.values)-1, font=font, **kwargs
		)
		self.text = Label(self, font=font, width=4, bg=bg)
		self.slide.pack(side=RIGHT, expand=1, fill=X)
		self.text.pack(side=TOP, fill=BOTH, padx=5)

#A frame that can be expanded and collapsed by clicking on the title
class expandableFrame(Frame):
	def __init__(self, parent=None, text="", fg='#333', bg='#FFF', padx=8, pady=None, font=None, startOpen=True):
		Frame.__init__(self, parent, bg=bg)
		self.columnconfigure(0, weight=1)
		
		self.pady=pady
		self.padx=padx
		
		self.text = text
		self.titleLabel = Label(self, fg=fg, bg=bg, font=font, cursor='hand2')
		self.titleLabel.bind('<Button-1>', self.toggle)
		self.titleLabel.grid(row=0, column=0, sticky='WE', pady=(pady, 2))
		
		self.open = IntVar()
		self.subframe = Frame(self, padx=padx, pady=0, bg=bg)
		self.open.set(int(not startOpen))
		self.toggle()
	
	def toggle(self, event=None):
		if bool(self.open.get()):	#If open, close
			self.subframe.grid_forget()
			self.titleLabel['text'] = self.text+' '+'▸'
			self.open.set(0)
		else:						#If closed, open
			self.subframe.grid(row=1, column=0, padx=self.padx, pady=0, sticky='WE')
			self.titleLabel['text'] = self.text+' '+'▾'
			self.open.set(1)

# A checkbox-like widget whose toggle is the entire element
# bg and fg take a two-element tuple for inactive and active states
class textCheck(Label):
	def __init__(self, parent=None, text=None, bg=('#FFFFFF','#419BF9'), fg=('#333333','#FFFFFF'),
		font=('Lucida Grande',12), defaultValue=False, anchor='w'
	):
		super().__init__(parent, text=text, bg=bg[defaultValue], fg=fg[defaultValue], anchor=anchor)
		self.bg = (Color(bg[0]), Color(bg[1]))
		self.fg = (Color(fg[0]), Color(fg[1]))
		
		#Generate disabled and hover colors
		self.disabledbg = (
			self.bg[0],
			Color(hue=self.bg[1].hue, saturation=self.bg[1].saturation, luminance=.5+self.bg[1].luminance/2)
		)
		self.disabledfg = (
			Color(hue=self.fg[0].hue, saturation=self.fg[0].saturation, luminance=.5+self.fg[0].luminance/2),
			Color(hue=self.fg[1].hue, saturation=self.fg[1].saturation, luminance=.5+self.fg[1].luminance/2)
		)
		hoverbg = (
			Color(hue=self.bg[0].hue, saturation=self.bg[0].saturation, luminance=self.bg[0].luminance-0.075 if self.bg[0].luminance-0.075 > 0 else 0),
			Color(hue=self.bg[1].hue, saturation=self.bg[1].saturation, luminance=self.bg[1].luminance-0.075 if self.bg[1].luminance-0.075 > 0 else 0)
		)
		hoverfg = (
			Color(hue=self.fg[0].hue, saturation=self.fg[0].saturation, luminance=self.fg[0].luminance-0.075 if self.fg[0].luminance-0.075 > 0 else 0),
			Color(hue=self.fg[1].hue, saturation=self.fg[1].saturation, luminance=self.fg[1].luminance-0.075 if self.fg[1].luminance-0.075 > 0 else 0)
		)
		
		self.value = defaultValue
		self.enabled = True
		
		def hover(event):
			if self.enabled: self.config(bg=hoverbg[self.value], fg=hoverfg[self.value])
		def leave(event):
			if self.enabled: self.config(bg=self.bg[self.value], fg=self.fg[self.value])
		
		self.bind('<Button-1>', self.toggle)
		self.bind('<Enter>', hover)
		self.bind('<Leave>', leave)
	
	def get(self): return self.value
	def set(self, value):
		if not self.enabled: return
		
		self.value = bool(value)
		self.config(bg=self.bg[self.value], fg=self.fg[self.value])
	
	def toggle(self, event=None): self.set(not self.value)
	
	def enable(self): self.disabled(False)
	def disable(self): self.disabled(True)
	def disabled(self, disable):
		if disable:
			bg = self.disabledbg
			fg = self.disabledfg
		else:
			bg = self.bg
			fg = self.fg
		
		self.enabled = not bool(disable)
		self.config(bg=bg[self.value], fg=fg[self.value])

# A checkbox that enables/disables a text box
class checkEntry(Frame):
	def __init__(self, parent=None, title=None, width=20, bg='#FFFFFF', font=('Lucida Grande', 12), default='', type='string', callback=None):
		Frame.__init__(self, parent, bg=bg)
		
		#If we're enforcing int, don't allow nonnumerical input
		self.type=type
		if type=='int':
			validate='key'
			def validateInt(code, newval):		
				if code != '1': return True
				for c in newval:
					if c not in '0123456789':
						return False
				return True
			valint = self.register(validateInt)
			valf = (valint, '%d', '%S')
		else:
			validate='none'
			valf = None
			
		self.enabled = True
		self.entryValue = StringVar()
		self.entryValue.set(default)
		self.textbox = Entry(self, textvariable=self.entryValue, width=width, state='disabled', validate=validate, validatecommand=valf, highlightbackground=bg)
		self.textbox.grid(row=0, column=1)
		self.callback = callback
		
		self.checkVar = BooleanVar()
		self.checkbox = Checkbutton(self, text=title, bg=bg, var=self.checkVar, onvalue=True, offvalue=False, command=self.disableTextfield)
		self.checkbox.grid(row=0, column=0)
	
	def disableTextfield(self):
		self.textbox.config(state='disabled' if not self.checkVar.get() else 'normal')
		if callable(self.callback): self.callback(self.get())
	
	#Return False or the value of the textbox
	def get(self):
		if not self.checkVar.get(): return False
		v = self.entryValue.get()
		if self.type=='int':
			return 0 if v=='' else int(v)
		else: return v
	
	#Can pass a bool to turn on and off the checkbox, or a string or an int (depending on the type)
	#to change the value of the textbox.
	def set(self, val):
		if isinstance(val, bool):
			self.checkVar.set(val)
		elif isinstance(val, str) or isinstance(val, int):
			if self.type=='int': val=int(val)
			self.checkVar.set(True)
			self.entryValue.set(val)
		self.disableTextfield()
	
	def enable(self): self.disabled(False)
	def disable(self): self.disabled(True)
	def disabled(self, disable):
		self.textbox.config(state='disabled' if disable else 'normal')
		self.checkbox.config(state='disabled' if disable else 'normal')
		self.enabled = not disable

#Requires random and not numpy.random for some reason??
def randomword(length):
	return ''.join(rand2.choice(string.ascii_lowercase) for i in range(length))