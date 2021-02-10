# ==========
# The standalone Tkinter-based control panel interface
# Do not run this file; import model.py and run from your file.
# ==========

from tkinter import *
from tkinter.ttk import Progressbar
from helipad.helpers import Color
import sys, colorsys
from helipad.param import Param
from math import ceil

class Cpanel:	
	def __init__(self, model):
		self.model = model
		self.parent = Tk()
		try:
			import Pmw
			self.balloon = Pmw.Balloon(self.parent)
			textCheck.pmw = self.balloon
		except:
			self.balloon = None
			print('Use pip to install Pmw in order to use tooltips')
		
		bgcolors = ('#FFFFFF','#EEEEEE')
		fnum = 1
		
		#
		# CALLBACK FUNCTION GENERATORS FOR TKINTER ELEMENTS
		#		
		def setVar(param, item=None):
			def sv(val=None):
				#Different widgets send different things to the callback…
				if param.type=='slider': val = float(val)
				elif param.type=='menu': val = {y:x for x,y in param.opts.items()}[val]
				elif param.type=='check': val = (param.element if item is None else param.element[item]).BooleanVar.get()
				
				#Parameters that don't update automatically
				if param.type in ['slider', 'menu', 'check']: param.set(val, item, updateGUI=False)
				
				if callable(param.callback):
					if param.obj is None: param.callback(self.model, param.name, val)
					else: param.callback(self.model, param.name, item, val)
			return sv
		Param.setVar = setVar
		
		#For shock buttons.
		#Can't do an inline lambda here because lambdas apparently don't preserve variable context
		def shockCallback(name):
			return lambda: self.model.shocks[name].do(self.model)
		
		class progressBar(Progressbar):
			def __init__(self, determinate=True, root=None):
				super().__init__(root, length=250, style="whitebg.Horizontal.TProgressbar")
				self.determinate(determinate, False)
				self.running = False
			
			@property
			def mode(self):
				#Windows returns a string here, and MacOS returns an object
				mode = self.cget('mode')
				return mode if isinstance(mode, str) else self.cget('mode').string
			
			def determinate(self2, det, refresh=True):
				self2.config(mode='determinate' if det else 'indeterminate')
				if det: super().stop()
				elif self2.running: super().start()
				if refresh: self.parent.update()
			def update(self, n): self['value'] = n*100
			def start(self):
				if self.mode =='indeterminate': super().start()
			def stop(self):
				if self.mode =='indeterminate':
					super().stop()
					self.update(1)
			def done(self):
				self.stop()
				self.update(0)
		
		class runButton(Button):
			def __init__(self2, root, bg='#EEEEEE'):
				super().__init__(root, text='Run', command=self.model.launchVisual, padx=10, pady=10, highlightbackground=bg)
			
			def run(self2):
				self2['text'] = 'Pause'
				self2['command'] = self.model.stop
			
			def pause(self2):
				self2['text'] = 'Run'
				self2['command'] = self.model.start
			
			def terminate(self2):
				self2['text'] = 'New Model'
				self2['command'] = self.model.launchVisual
		
		#
		# CONSTRUCT CONTROL PANEL INTERFACE
		#
		
		def drawCircle(frame, color, bg):
			circle = Canvas(frame, width=17, height=12, bg=bg, highlightthickness=0)
			circle.create_oval(0,0,12,12,fill=color, outline='')
			return circle
		
		def renderParam(frame, param, item=None, bg='#EEEEEE'):
			if param.type in ['hidden', 'checkgrid']: return
	
			if param.obj is not None and item is None:
				expFrame = expandableFrame(frame, bg=bg, padx=5, pady=10, text=param.title, fg="#333", font=font)
				efSub = expFrame.subframe
				i=0
				param.element = {}
				for name, b in param.keys.items():
					if hasattr(b, 'money') and b.money: continue
			
					#Do this separately because they should all be stacked
					f = renderParam(efSub, param, item=name, bg=bg)
					if param.type == 'checkentry':
						f.grid(row=i, column=0)
						efSub.columnconfigure(0,weight=1)
					
					#Everything else goes in the two-column format
					else:					
						f.grid(row=ceil((i+1)/2)*2, column=i%2)
						for c in range(2): efSub.columnconfigure(c, weight=1)
			
					i+=1
				return expFrame
			else:
				title = param.title if item is None else item.title()
				wrap = Frame(frame, bg=bg, padx=10 if item is None and not getattr(param,'config',False) else 0, pady=8 if item is None and not getattr(param,'config',False) else 0)
				
				#Get .value directly rather than .get because we need the Var() items
				#Except for checkentry since it doesn't store its values in .value
				if param.value is not None:
					val = param.value if item is None else param.value[item]
				
				#These put the circle beside the widget
				if param.type in ['check', 'checkentry']:
					if param.type=='check':
						v = BooleanVar(value=val)
						el = Checkbutton(wrap, text=title, var=v, onvalue=True, offvalue=False, command=param.setVar(item), bg=bg)
						el.BooleanVar = v
					elif param.type=='checkentry':
						dflt = param.get(item)
						el = checkEntry(wrap, title, bg=bg, width=15, padx=0 if getattr(param,'config',False) else 10, pady=0 if getattr(param,'config',False) else 5, type='int' if param.entryType is int else 'string', command=param.setVar(item))
						if param.name=='stopafter' and param.event:
							el.disable()
							el.entryValue.set('Event: '+param.get())
							el.checkVar.set(True)
							el.textbox.config(font=('Helvetica Neue', 12,'italic')) #Lucida doesn't have an italic?
						else: el.set(dflt)
					el.grid(row=0, column=1)
					if item is not None: drawCircle(wrap, param.keys[item].color.hex, bg).grid(row=0, column=0)
		
				#These need a separate label
				else:					
					if param.type == 'menu':
						v = StringVar(value=param.opts[val])
						el = OptionMenu(wrap, v, *param.opts.values(), command=param.setVar(item))
						el.StringVar = v #Save to set later
						el.config(bg=bg)
					elif param.type == 'slider':
						if isinstance(param.opts, dict): el = Scale(wrap, from_=param.opts['low'], to=param.opts['high'], resolution=param.opts['step'], orient=HORIZONTAL, length=150, highlightthickness=0, command=param.setVar(item), bg=bg)
						else: el = logSlider(wrap, title=title if getattr(param, 'config', False) else None, orient=HORIZONTAL, values=param.opts, length=150, command=param.setVar(item), bg=bg)
						el.set(param.get(item))
						
					if item is None and not getattr(param, 'config', False):
						label = Label(wrap, text=title, fg="#333", bg=bg).pack(side=LEFT, padx=8, pady=3)
						el.pack(side=RIGHT)
					elif getattr(param, 'config', False): el.pack()
					else:
						lframe = Frame(wrap, bg=bg, padx=0, pady=0)
						label = Label(lframe, text=title, fg="#333", bg=bg).grid(row=0, column=1, pady=(0,8))
						drawCircle(lframe, param.keys[item].color.hex, bg).grid(row=0, column=0, pady=(0,8))
						lframe.grid(row=1, column=0)
						el.grid(row=0,column=0)
					
					if self.balloon and param.desc is not None: self.balloon.bind(el, param.desc)
				
				if item is None:
					param.element = el
				else: param.element[item] = el
				return wrap
		
		ctop = self.model.doHooks('CpanelTop', [self, bgcolors[fnum%2]])
		if ctop:
			ctop.pack(fill="x", side=TOP)
			fnum += 1
		
		frame1 = Frame(self.parent, padx=10, pady=10, bg=bgcolors[fnum%2])
		renderParam(frame1, self.model.params['stopafter'], bg=bgcolors[fnum%2]).grid(row=0,column=0, columnspan=3)
		renderParam(frame1, self.model.params['csv'], bg=bgcolors[fnum%2]).grid(row=1,column=0, columnspan=3)
		if not self.model.params['stopafter'].event: self.model.params['stopafter'].element.entryValue.set(10000)
		self.model.params['csv'].set('filename')
		self.model.params['csv'].set(False)
		
		font = ('Lucida Grande', 16) if sys.platform=='darwin' else ('Calibri', 14)
		
		renderParam(frame1, self.model.params['refresh'], bg=bgcolors[fnum%2]).grid(row=2, column=0, columnspan=2, pady=(10,0))
		self.runButton = runButton(frame1, bgcolors[fnum%2])
		self.runButton.grid(row=2, column=2, pady=(15,0))
		
		for c in range(2): frame1.columnconfigure(c, weight=1)
		frame1.pack(fill="x", side=TOP)
		fnum += 1
		
		#Can't change the background color of a progress bar on Mac, so we have to put a gray stripe on top :-/
		frame0 = Frame(self.parent, padx=10, pady=0, bg=bgcolors[1])
		self.progress = progressBar(root=frame0)
		self.progress.grid(row=0, column=0)
		frame0.columnconfigure(0,weight=1)
		frame0.pack(fill="x", side=TOP)
		
		caip = self.model.doHooks('CpanelAboveItemParams', [self, bgcolors[fnum%2]])
		if caip:
			caip.pack(fill="x", side=TOP)
			fnum += 1
		
		for k, param in model.goodParams.items():
			e = renderParam(None, param, bg=bgcolors[fnum%2])
			if e is not None: e.pack(fill="x")
		if model.goodParams != {}: fnum += 1 #Only increment the stripe counter if we had any good params to draw
		for p,v in model.primitives.items():
			if v.breedParams != {}:
				for k, param in v.breedParams.items():
					e = renderParam(None, param, bg=bgcolors[fnum%2])
					if e is not None: e.pack(fill="x")
				fnum += 1
		
		cap = self.model.doHooks('CpanelAboveParams', [self, bgcolors[fnum%2]])
		if cap:
			cap.pack(fill="x", side=TOP)
			fnum += 1
		
		#Parameter sliders
		for k, param in self.model.params.items():
			if not getattr(param, 'config', False):
				e = renderParam(self.parent, param, bg=bgcolors[fnum%2])
				if e is not None: e.pack(fill=None if param.type=='check' else X)
		fnum += 1
		
		#Checkgrid parameters
		for p in self.model.params.values():
			if p.type!='checkgrid' or p.name=='shocks': continue
			cg = checkGrid(parent=self.parent, text=p.title, columns=getattr(p, 'columns', 3), bg=bgcolors[fnum%2], callback=p.setVar())
			for k,v in p.opts.items():
				if not isinstance(v, (tuple, list)): v = (v, None)
				elif len(v) < 2: v = (v[0], None)
				cg.addCheck(k, v[0], p.vars[k], v[1])
			p.element = cg
			p.element.pack(fill=BOTH)
			fnum += 1
		
		cas = self.model.doHooks('CpanelAboveShocks', [self, bgcolors[fnum%2]])
		if cas:
			cas.pack(fill="x", side=TOP)
			fnum += 1
		
		#Shock checkboxes and buttons
		if self.model.shocks.number > 0:
			frame8 = expandableFrame(self.parent, text='Shocks', padx=5, pady=8, font=font, bg=bgcolors[fnum%2])
			frame8.checks = {}
			active = self.model.param('shocks')
			self.model.params['shocks'].element = frame8
			for shock in self.model.shocks.shocksExceptButtons.values():
				bv = BooleanVar(value=shock.name in active)
				shock.element = Checkbutton(frame8.subframe, text=shock.name, var=bv, onvalue=True, offvalue=False, bg=bgcolors[fnum%2], anchor=W, command=shock.setCallback)
				shock.element.BooleanVar = bv #To set via the shock object
				frame8.checks[shock.name] = bv #To set via the shock parameter
				if self.balloon and shock.desc is not None: self.balloon.bind(shock.element, shock.desc)
				shock.element.pack(fill=BOTH)
			
			b=0
			if len(self.model.shocks.buttons):
				bframe = Frame(frame8.subframe, bg=bgcolors[fnum%2])
				for c in range(2): bframe.columnconfigure(c ,weight=1)
				for shock in self.model.shocks.buttons.values():
					shock.element = Button(bframe, text=shock.name, command=shockCallback(shock.name), padx=10, pady=10, highlightbackground=bgcolors[fnum%2])
					shock.element.grid(row=3+int(ceil((b+1)/2)), column=b%2, sticky='W')
					if self.balloon and shock.desc is not None: self.balloon.bind(shock.element, shock.desc)
					b+=1
				bframe.pack(fill=BOTH)
			frame8.pack(fill="x", side=TOP)
		
		cbot = self.model.doHooks('CpanelBottom', [self, bgcolors[fnum%2]])
		if cbot:
			cbot.pack(fill="x", side=TOP)
			fnum += 1
		
		#Set application name
		self.parent.title(self.model.name+(' ' if self.model.name!='' else '')+'Control Panel')
		self.parent.resizable(0,0)
		if sys.platform=='darwin':
			try:
				from Foundation import NSBundle
				bundle = NSBundle.mainBundle()
				if bundle:
					info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
					if info and info['CFBundleName'] == 'Python':
						info['CFBundleName'] = 'Helipad'
			except: print('Use pip to install pyobjc for nice Mac features')
	
	#Step one period at a time and update the graph
	#For use in debugging
	def step(self):
		t = self.model.step()
		self.model.graph.update(self.model.data.getLast(1))
		return t

#
# MISCELLANEOUS INTERFACE ELEMENTS
#

# A slider with defined non-linear intervals
class logSlider(Frame):	
	def __init__(self, parent=None, title=None, command=None, bg='#FFFFFF', font=('Lucida Grande',12), values=(), **kwargs):
		Frame.__init__(self, parent, bg=bg)
		self.label = Label(self, font=font, text=title, bg=bg).pack(side=TOP) if title else None
		self.values = values
		self.extCommand = command
		self.number = values[0]
		
		#Receives an index from the slider and sets the value
		def setText(idx):
			self.number = self.values[int(idx)]
			self.text.configure(text=self.values[int(idx)])
			if self.extCommand != None: self.extCommand(self.values[int(idx)])
		
		self.slide = Scale(self, command=setText,
			bg=bg, showvalue=0, from_=0, to=len(self.values)-1, font=font, **kwargs
		)
		self.text = Label(self, font=font, width=4, bg=bg)
		self.slide.pack(side=RIGHT, expand=1, fill=X)
		self.text.pack(side=TOP, fill=BOTH, padx=5)
		
	def get(self): return self.number
	
	#Receives a value externally and sets the slider to an index
	def set(self, val):
		self.number = val
		if val in self.values: self.slide.set(self.values.index(val))
		self.text.configure(text=val)
	
	def enable(self): self.disabled(False)
	def disable(self): self.disabled(True)
	def disabled(self, val):
		if val:
			self.text.configure(fg='#999')
			if self.label is not None: self.label.configure(fg='#999')
			self.slide.configure(state='disabled')
		else:
			self.text.configure(fg='#333')
			if self.label is not None: self.label.configure(fg='#333')
			self.slide.configure(state='normal')
	
	#Here for compatibility with other Tkinter widgets
	def configure(self, state): self.disabled(state=='disabled')

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
		
		def darken(color):
			hls = colorsys.rgb_to_hls(*color.rgb)
			return Color(colorsys.hls_to_rgb(hls[0], hls[1]-0.075 if hls[1]>0.075 else 0, hls[2]))
		
		#Generate disabled and hover colors
		self.disabledbg = (self.bg[0], self.bg[1].lighten(2))
		self.disabledfg = (self.fg[0].lighten(2), self.fg[1].lighten(2))
		hoverbg = (darken(self.bg[0]), darken(self.bg[1]))
		hoverfg = (darken(self.fg[0]), darken(self.fg[1]))
		
		self.value = defaultValue
		self.enabled = True
		
		def hover(event):
			if self.enabled: self.config(bg=hoverbg[self.value].hex, fg=hoverfg[self.value].hex)
		def leave(event):
			if self.enabled: self.config(bg=self.bg[self.value].hex, fg=self.fg[self.value].hex)
		
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
		self.config(bg=self.bg[self.value].hex, fg=self.fg[self.value].hex)
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
		self.config(bg=bg[self.value].hex, fg=fg[self.value].hex)

# A checkbox that enables/disables a text box
class checkEntry(Frame):
	def __init__(self, parent=None, title=None, width=20, bg='#FFFFFF', font=('Lucida Grande', 12), padx=0, pady=0, default='', type='string', command=None):
		Frame.__init__(self, parent, bg=bg, padx=padx, pady=pady)
		
		#If we're enforcing int, don't allow nonnumerical input
		self.type=type
		def validate(code, insert, oldval, newval):
			if not self.enabled: return
			allow = True
			if self.type=='int' and code == '1':
				for c in insert:
					if c not in '0123456789':
						allow = False
			if allow: self.callback(int(newval) if self.type=='int' and newval!='' else newval)
			return allow
		valint = self.register(validate)
			
		self.enabled = True
		self.entryValue = StringVar()
		self.entryValue.set(default)
		self.textbox = Entry(self, textvariable=self.entryValue, width=width, state='disabled', validate='key', validatecommand=(valint, '%d', '%S', '%s', '%P'), highlightbackground=bg)
		self.textbox.grid(row=0, column=1)
		self.callback = command
		
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
			if self.type=='int' and val!='': val=int(val)
			self.checkVar.set(True)
			self.entryValue.set(val)
		self.disableTextfield()
	
	def enable(self): self.disabled(False)
	def disable(self): self.disabled(True)
	def disabled(self, disable):
		self.checkbox.config(state='disabled' if disable else 'normal')
		self.textbox.config(state='disabled' if disable or not self.checkVar.get() else 'normal')
		self.enabled = not disable
	
	#Here for compatibility with other Tkinter widgets
	def configure(self, state): self.disabled(state=='disabled')

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
			def cbWrap(val): self.callback(val)
		else: cbWrap = None
		
		self.checks[var] = textCheck(self.subframe, text=text, anchor='w', defaultValue=defaultValue, bg=(self.bg, '#419BF9'), desc=desc, callback=cbWrap)
		self.checks[var].grid(row=int(ceil(len(self.checks)/self.columns)), column=(len(self.checks)-1)%self.columns, sticky='WE')
		return self.checks[var]
	
	def __getitem__(self, index): return self.checks[index].get()
	def __setitem__(self, index, value): self.checks[index].set(value)
	
	def items(self): return self.checks.items()
	def values(self): return self.checks.values()
	def keys(self): return self.checks.keys()
	def disabled(self, key, val=None):
		if isinstance(key, bool):
			if key: self.disable()
			else: self.enable()
		else: self.checks[key].disabled(val)
	def enable(self, key=None):
		if key: self.checks[key].enable()
		else:
			for c in self.values(): c.enable()
	def disable(self, key=None):
		if key: self.checks[key].disable()
		else:
			for c in self.values(): c.disable()
	def configure(self, state): self.disabled(state=='disabled')