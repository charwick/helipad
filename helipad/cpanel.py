# ==========
# The standalone Tkinter-based control panel interface
# Do not run this file; import model.py and run from your file.
# ==========

from tkinter import *
from tkinter.ttk import Progressbar
from colour import Color
from math import ceil
# import time #For performance testing

class GUI():	
	def __init__(self, parent, model, headless=False):
		self.parent = parent
		self.model = model
		try:
			import Pmw
			self.balloon = Pmw.Balloon(parent)
			textCheck.pmw = self.balloon
		except:
			self.balloon = None
			print('Use pip to install Pmw in order to use tooltips')
		self.updateEvery = 20
		self.headless = headless
		
		bgcolors = ('#FFFFFF','#EEEEEE')
		fnum = 1
		
		#
		# CALLBACK FUNCTION GENERATORS FOR TKINTER ELEMENTS
		#		
		def setVar(param, item=None):
			def sv(val=None):
				if callable(param.callback):
					if param.obj is None: param.callback(self.model, param.name, param.get(item))
					else: param.callback(self.model, param.name, item, param.get(item))
				
				#If it's a slider, the parameter doesn't update automatically
				if param.type=='slider': param.set(float(val), item, updateGUI=False)
			return sv
		
		#For shock buttons.
		#Can't do an inline lambda here because lambdas apparently don't preserve variable context
		def shockCallback(name):
			return lambda: self.model.shocks[name].do(self.model)
		
		#Toggle the progress bar between determinate and indeterminate when stopafter gets changed
		def switchPbar(val):
			if not val:
				self.progress.config(mode='indeterminate')
				if self.model.running: self.progress.start()
			else:
				self.progress.config(mode='determinate')
				if self.model.running: self.progress.stop()
			self.model.root.update()
		
		#
		# CONSTRUCT CONTROL PANEL INTERFACE
		#
		
		gtop = self.model.doHooks('GUITop', [self, bgcolors[fnum%2]])
		if gtop:
			gtop.pack(fill="x", side=TOP)
			fnum += 1
		
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
		self.runButton = Button(frame1, text='Run', command=self.run, padx=10, pady=10, highlightbackground=bgcolors[fnum%2])
		self.runButton.grid(row=2, column=2, pady=(15,0))
		
		#Buttons
		b=0
		for f in self.model.buttons:
			button = Button(frame1, text=f[0], command=f[1], padx=10, pady=10, highlightbackground=bgcolors[fnum%2])
			button.grid(row=3+int(ceil((b+1)/2)), column=b%2, pady=(15,0))
			if self.balloon and f[2] is not None: self.balloon.bind(button, f[2])
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
		
		gaip = self.model.doHooks('GUIAboveItemParams', [self, bgcolors[fnum%2]])
		if gaip:
			gaip.pack(fill="x", side=TOP)
			fnum += 1
		
		#Item parameter sliders
		def buildSlider(itemDict, paramDict, prim=None, fnum=fnum):
			for k, param in paramDict.items():
				bpf_super = expandableFrame(bg=bgcolors[fnum%2], padx=5, pady=10, text=param.title, fg="#333", font=font)
				bpf = bpf_super.subframe
				
				i=0
				param.element = {}
				for name, b in itemDict.items():
					
					#Circle for item color
					lframe = Frame(bpf, bg=bgcolors[fnum%2], padx=0, pady=0)
					c = Canvas(lframe, width=17, height=12, bg=bgcolors[fnum%2], highlightthickness=0)
					c.create_oval(0,0,12,12,fill=b.color.hex_l, outline='')
					c.grid(row=0, column=0, pady=(0,8))
					
					#Item name label
					if param.type != 'check':
						Label(lframe, text=name.title(), fg="#333", bg=bgcolors[fnum%2]).grid(row=0, column=1, pady=(0,8))
				
						if param.type == 'menu':
							param.element[name] = OptionMenu(bpf, param.value[name], command=setVar(param, name), *param.opts.values())
							param.element[name].config(bg=bgcolors[fnum%2])
						elif param.type == 'slider':
							param.element[name] = Scale(bpf, from_=param.opts['low'], to=param.opts['high'], resolution=param.opts['step'], orient=HORIZONTAL, length=150, highlightthickness=0, command=setVar(param, name), bg=bgcolors[fnum%2])
							param.element[name].set(param.get(name))
						
						param.element[name].grid(row=ceil((i+1)/2)*2-1, column=i%2)
					
					#Do everything differently if we've got a checkbox
					else:
						param.element[name] = Checkbutton(lframe, text=name.title(), var=param.value[name], onvalue=True, offvalue=False, command=setVar(param, name), bg=bgcolors[fnum%2])
						param.element[name].variable = param.value[name] #Keep track of this because it doesn't pass the value to the callback
						param.element[name].grid(row=0, column=1)
					
					bpf.columnconfigure(0,weight=1)
					bpf.columnconfigure(1,weight=1)
					lframe.grid(row=ceil((i+1)/2)*2, column=i%2)
					if self.balloon and param.desc is not None: self.balloon.bind(param.element[name], param.desc)
					
					i+=1
				bpf_super.pack(fill="x", side=TOP)
				
		buildSlider(model.nonMoneyGoods, model.goodParams, fnum=fnum)
		if model.goodParams != {}: fnum += 1 #Only increment the stripe counter if we had any good params to draw
		for p,v in model.primitives.items():
			if v.breedParams != {}:
				buildSlider(v.breeds, v.breedParams, prim=p, fnum=fnum)
				fnum += 1
		
		gap = self.model.doHooks('GUIAboveParams', [self, bgcolors[fnum%2]])
		if gap:
			gap.pack(fill="x", side=TOP)
			fnum += 1
		
		#Parameter sliders
		for k, param in self.model.params.items():
			if param.type == 'hidden': continue
			elif param.type == 'check':
				f = Frame(self.parent, bg=bgcolors[fnum%2], pady=5)
				param.element = Checkbutton(f, text=param.title, var=param.value, onvalue=True, offvalue=False, command=setVar(param), bg=bgcolors[fnum%2])
				param.element.variable = param.value #Keep track of this because it doesn't pass the value to the callback
				param.element.pack()
			else:
				f = Frame(self.parent, bg=bgcolors[fnum%2], padx=10, pady=8)
				Label(f, text=param.title, fg="#333", bg=bgcolors[fnum%2]).pack(side=LEFT, padx=8, pady=3)
				if param.type == 'menu':
					#Callback is different because menus automatically update their variable
					param.element = OptionMenu(f, param.value, *param.opts.values(), command=setVar(param))
					param.element.config(bg=bgcolors[fnum%2])
				elif param.type == 'slider':
					param.element = Scale(f, from_=param.opts['low'], to=param.opts['high'], resolution=param.opts['step'], orient=HORIZONTAL, length=150, highlightthickness=0, command=setVar(param), bg=bgcolors[fnum%2])
					param.element.set(param.value)
					
				param.element.pack(side=RIGHT)
				if self.balloon and param.desc is not None: self.balloon.bind(param.element, param.desc)
				
			f.pack(fill="x", side=TOP)
		fnum += 1
		
		gapl = self.model.doHooks('GUIAbovePlotList', [self, bgcolors[fnum%2]])
		if gapl:
			gapl.pack(fill="x", side=TOP)
			fnum += 1
		
		# Graph Checkboxes
		def plotCallback(name, val):
			self.model.plots[name].active(val, updateGUI=False)
		self.checks = checkGrid(self.parent, text='Plots', padx=5, pady=8, font=font, bg=bgcolors[fnum%2], columns=3, callback=plotCallback)
		for k, plot in self.model.plots.items():
			plot.check = self.checks.addCheck(k, plot.label, plot.selected)
		self.checks.pack(fill="x", side=TOP)
		
		gas = self.model.doHooks('GUIAboveShocks', [self, bgcolors[fnum%2]])
		if gas:
			gas.pack(fill="x", side=TOP)
			fnum += 1
		
		#Shock checkboxes
		if self.model.shocks.number > 0:
			fnum += 1
			frame8 = expandableFrame(self.parent, text='Shocks', padx=5, pady=8, font=font, bg=bgcolors[fnum%2])
			for shock in self.model.shocks.shocks.values():
				if callable(shock.timerFunc):
					shock.guiElement = Checkbutton(frame8.subframe, text=shock.name, var=shock.boolvar, onvalue=True, offvalue=False, bg=bgcolors[fnum%2], anchor=W)
				elif shock.timerFunc == 'button':
					shock.guiElement = Button(frame8.subframe, text=shock.name, command=shockCallback(shock.name), padx=10, pady=10)
				
				if self.balloon and shock.desc is not None:
					self.balloon.bind(shock.guiElement, shock.desc)
				shock.guiElement.pack(fill=BOTH)
			frame8.pack(fill="x", side=TOP)
		
		gbot = self.model.doHooks('GUIBottom', [self, bgcolors[fnum%2]])
		if gbot:
			gbot.pack(fill="x", side=TOP)
			fnum += 1
		
		#Set application name
		if sys.platform=='darwin':
			try:
				from Foundation import NSBundle
				bundle = NSBundle.mainBundle()
				if bundle:
					info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
					if info and info['CFBundleName'] == 'Python':
						info['CFBundleName'] = 'Helipad'
			except: print('Use pip to install pyobjc for nice Mac features')
		
		def updateGraph(model):
			if model.t%model.gui.updateEvery != 0: return
			if model.graph is not None:
				data = model.gui.model.data.getLast(model.t - model.lastUpdate)
	
				if (model.graph.resolution > 1):
					data = {k: keepEvery(v, model.graph.resolution) for k,v in data.items()}
				model.graph.update(data)
				model.lastUpdate = model.t
				if model.graph.resolution > model.gui.updateEvery: model.gui.updateEvery = model.graph.resolution
			
			## Performance indicator
			# newtime = time.time()
			# print('Period', t, 'at', model.gui.updateEvery/(newtime-self.start), 'periods/second')
			# self.start = newtime
	
			st = model.gui.stopafter.get()
			if st:
				model.gui.progress['value'] = model.t/st*100
				if model.graph is None: model.root.update() #Make sure we don't hang the interface if plotless
				if model.t>=st: model.gui.terminate()
		self.model.addHook('modelPostStep', updateGraph)
		
		#Passes itself to the callback
		self.model.doHooks('GUIPostInit', [self])
	
	#Resume a model
	def run(self):
		if hasattr(self, 'runButton'):
			self.runButton['text'] = 'Pause'
			self.runButton['command'] = self.pause
		
		#Adjust progress bar
		if not self.stopafter.get():
			self.progress.config(mode='indeterminate')
			self.progress.start()
		else:
			self.progress.config(mode='determinate')
		
		#self.start = time.time()
		if not self.model.hasModel: self.model.launchPlots()
		else: self.model.start()
		
		remainder = self.model.t % self.updateEvery
		if remainder > 0: self.model.graph.update(self.model.data.getLast(remainder)) #Last update at the end
	
	#Step one period at a time and update the graph
	#For use in debugging
	def step(self):
		t = self.model.step()
		self.model.graph.update(self.model.data.getLast(1))
		return t
	
	def pause(self):
		self.model.stop()
		self.progress.stop()
		self.runButton['text'] = 'Run'
		self.runButton['command'] = self.run
		self.model.doHooks('pause', [self])
	
	def terminate(self, evt=False):
		if self.model.running and (self.headless or self.expCSV.get()):
			self.model.data.saveCSV(self.expCSV.get() if not self.headless else 'data')
		
		self.model.stop()
		self.model.hasModel = False
		self.progress.stop()
		
		#Re-enable checkmarks and options
		self.checks.enable()
		for param in self.model.allParams:
			if not hasattr(param, 'element'): continue
			if isinstance(param.element, dict):
				for e in param.element.values(): e.configure(state='normal')
			else: param.element.configure(state='normal')
		self.stopafter.enable()
		self.expCSV.enable()
		
		#Passes GUI object and model data to the callback
		self.model.doHooks('terminate', [self, self.model.data.dataframe])
		
		if hasattr(self, 'runButton'):
			self.runButton['text'] = 'New Model'
			self.runButton['command'] = self.run

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
		font=('Lucida Grande',12), defaultValue=False, anchor='w', desc=None, callback=None
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
		
		#Have to do this *before* any other bindings because pmw.bind deletes all the others
		if hasattr(self, 'pmw') and desc: self.pmw.bind(self, desc)
		
		self.bind('<Button-1>', self.toggle, add='+')
		self.bind('<Enter>', hover, add='+')
		self.bind('<Leave>', leave, add='+')
		self.callback = callback
	
	def get(self): return self.value
	def set(self, value):
		if not self.enabled: return
		
		self.value = bool(value)
		self.config(bg=self.bg[self.value], fg=self.fg[self.value])
		if self.callback is not None: self.callback(value)
	
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

#An expandableFrame full of textChecks, with setters and getters.
class checkGrid(expandableFrame):
	def __init__(self, parent=None, text="", columns=3, fg='#333', bg='#FFF', padx=8, pady=5, font=('Lucida Grande', 16) if sys.platform=='darwin' else ('Calibri', 14), startOpen=True, callback=None):
		super().__init__(parent=parent, text=text, fg=fg, bg=bg, padx=padx, pady=pady, font=font, startOpen=startOpen)
		self.bg = bg
		self.columns = columns
		self.checks = {}
		self._index=0
		self.callback = callback
		
		for i in range(columns): self.subframe.columnconfigure(i,weight=1)
	
	def addCheck(self, var, text, defaultValue=True, desc=None):
		if self.callback is not None:
			def cbWrap(val): self.callback(var, val)
		else: cbWrap = None
		
		self.checks[var] = textCheck(self.subframe, text=text, anchor='w', defaultValue=defaultValue, bg=(self.bg, '#419BF9'), desc=desc, callback=cbWrap)
		self.checks[var].grid(row=int(ceil(len(self.checks)/self.columns)), column=(len(self.checks)-1)%self.columns, sticky='WE')
		return self.checks[var]
	
	def __getitem__(self, index): return self.checks[index].get()
	def __setitem__(self, index, value): self.checks[index].set(value)
	
	def items(self): return self.checks.items()
	def values(self): return self.checks.values()
	def keys(self): return self.checks.keys()
	def disabled(self, key, val):
		self.checks[key].disabled(val)
	def enable(self, key=None):
		if key: self.checks[key].enable()
		else:
			for c in self.values(): c.enable()
	def disable(self, key=None):
		if key: self.checks[key].disable()
		else:
			for c in self.values(): c.disable()