"""
The Tkinter-based control panel class for use in standalone models. This module should not be imported directly; use `model.launchCpanel()` instead.
"""

import tkinter as tk
import os, sys
from math import ceil
from tkinter.ttk import Progressbar
from helipad.helpers import Color, ï
from helipad.param import Param

class Cpanel(tk.Tk):
	"""The Tkinter-based control panel class for use in standalone models. https://helipad.dev/functions/cpanel/"""
	def __init__(self, model):
		self.model = model
		super().__init__()
		self.protocol("WM_DELETE_WINDOW", self.cpanelClose)

		#Set application name
		self.setAppIcon()
		self.title(ï('{}Control Panel').format(self.model.name+(' ' if self.model.name!='' else '')))
		self.resizable(0,0)

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
				elif param.type=='check': val = (param.element if item is None else param.elements[item]).BooleanVar.get()

				#Parameters that don't update automatically
				if param.type in ['slider', 'menu', 'check']: param.set(val, item, updateGUI=False)

				if callable(param.callback):
					if param.per is None: param.callback(self.model, param.name, val)
					else: param.callback(self.model, param.name, item, val)
			return sv
		Param.setVar = setVar

		#For shock buttons.
		#Can't do an inline lambda here because lambdas apparently don't preserve variable context
		def shockCallback(name: str):
			return lambda: self.model.shocks[name].do(self.model)

		class progressBar(Progressbar):
			def __init__(self, determinate: bool=True, root=None):
				super().__init__(root, length=250, style="whitebg.Horizontal.TProgressbar")
				self.determinate(determinate, False)
				self.running = False

			@property
			def mode(self):
				#Windows returns a string here, and MacOS returns an object
				mode = self.cget('mode')
				return mode if isinstance(mode, str) else self.cget('mode').string

			def determinate(self2, det: bool, refresh: bool=True):
				self2.config(mode='determinate' if det else 'indeterminate')
				if det: super().stop()
				elif self2.running: super().start()
				if refresh: self.update()
			def update(self, n): self['value'] = n*100
			def start(self):
				if self.mode =='indeterminate': super().start()
			def stop(self):
				if self.mode =='indeterminate':
					super().stop()
					self.update(1)
			def done(self):
				self.stop()
				self.config(mode='determinate')
				self.update(0)

		class runButton(tk.Button):
			def __init__(self2, root, bg='#EEEEEE'):
				super().__init__(root, text='Run', command=self.model.launchVisual, padx=10, pady=10, highlightbackground=bg)

			def run(self2):
				self2['text'] = ï('Pause')
				self2['command'] = self.model.stop

			def pause(self2):
				self2['text'] = ï('Run')
				self2['command'] = self.model.start

			def terminate(self2):
				self2['text'] = ï('New Model')
				self2['command'] = self.model.launchVisual

		#
		# CONSTRUCT CONTROL PANEL INTERFACE
		#

		def drawCircle(frame, color, bg):
			circle = tk.Canvas(frame, width=17, height=12, bg=bg, highlightthickness=0)
			circle.create_oval(0,0,12,12,fill=color, outline='')
			return circle

		def renderParam(frame, param, item=None, bg='#EEEEEE'):
			if param.type in ['hidden', 'checkgrid']: return

			#Parent frame for per-item parameters
			if param.per is not None and item is None:
				param.element = expandableFrame(frame, bg=bg, padx=5, pady=10, text=param.title, fg="#333", font=font)
				efSub = param.element.subframe
				i=0
				param.elements = {}
				for name, b in param.pKeys.items():
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
				return param.element

			#Single parameters, including the individual per-item parameters
			else:
				title = param.title if item is None else item.title()
				wrap = tk.Frame(frame, bg=bg, padx=10 if item is None and not getattr(param,'config',False) else 0, pady=8 if item is None and not getattr(param,'config',False) else 0)

				#Get .value directly rather than .get because we need the Var() items
				#Except for checkentry since it doesn't store its values in .value
				if param.value is not None:
					val = param.value if item is None else param.value[item]

				#These put the circle beside the widget
				if param.type in ['check', 'checkentry']:
					if param.type=='check':
						v = tk.BooleanVar(value=val)
						el = tk.Checkbutton(wrap, text=title, var=v, onvalue=True, offvalue=False, command=param.setVar(item), bg=bg)
						el.BooleanVar = v
					elif param.type=='checkentry':
						dflt = param.get(item)
						el = checkEntry(wrap, title, bg=bg, width=15, padx=0 if getattr(param,'config',False) else 10, pady=0 if getattr(param,'config',False) else 5, datatype='int' if param.entryType is int else 'string', command=param.setVar(item))
						if param.name=='stopafter' and param.event:
							el.disable()
							el.entryValue.set('Event: '+param.get())
							el.checkVar.set(True)
							el.textbox.config(font=('Helvetica Neue', 12,'italic')) #Lucida doesn't have an italic?
						else: el.set(dflt)

					if item is not None:
						el.grid(row=0, column=1)
						drawCircle(wrap, param.pKeys[item].color.hex, bg).grid(row=0, column=0)
					else: el.pack(anchor='center' if param.type=='check' else 'w')

				#These need a separate label
				else:
					if param.type == 'menu':
						v = tk.StringVar(value=param.opts[val])
						el = tk.OptionMenu(wrap, v, *param.opts.values(), command=param.setVar(item))
						el.StringVar = v #Save to set later
						el.config(bg=bg)
					elif param.type == 'slider':
						if isinstance(param.opts, dict): el = tk.Scale(wrap, from_=param.opts['low'], to=param.opts['high'], resolution=param.opts['step'], orient='horizontal', length=150, highlightthickness=0, command=param.setVar(item), bg=bg)
						else: el = logSlider(wrap, title=title if getattr(param, 'config', False) else None, orient='horizontal', values=param.opts, length=150, command=param.setVar(item), bg=bg)
						el.set(param.get(item))

					if item is None and not getattr(param, 'config', False):
						tk.Label(wrap, text=title, fg="#333", bg=bg).pack(side='left', padx=8, pady=3)
						el.pack(side='right')
					elif getattr(param, 'config', False): el.pack()
					else:
						lframe = tk.Frame(wrap, bg=bg, padx=0, pady=0)
						tk.Label(lframe, text=title, fg="#333", bg=bg).grid(row=0, column=1, pady=(0,8))
						drawCircle(lframe, param.pKeys[item].color.hex, bg).grid(row=0, column=0, pady=(0,8))
						lframe.grid(row=1, column=0)
						el.grid(row=0,column=0)

				if param.desc is not None: Tooltip(wrap, param.desc)

				if item is None: param.element = el
				else: param.elements[item] = el
				return wrap

		ctop = self.model.doHooks('CpanelTop', [self, bgcolors[fnum%2]])
		if ctop:
			ctop.pack(fill='x', side='top')
			fnum += 1

		frame1 = tk.Frame(self, padx=10, pady=10, bg=bgcolors[fnum%2])
		renderParam(frame1, self.model.params['stopafter'], bg=bgcolors[fnum%2]).grid(row=0,column=0, columnspan=3, sticky='w')
		renderParam(frame1, self.model.params['csv'], bg=bgcolors[fnum%2]).grid(row=1,column=0, columnspan=3, sticky='w')
		if not self.model.params['stopafter'].event and not self.model.param('stopafter'): self.model.params['stopafter'].element.entryValue.set(10000)
		self.model.params['csv'].set(ï('filename'))
		self.model.params['csv'].set(False)

		font = ('Lucida Grande', 16) if sys.platform=='darwin' else ('Calibri', 14)

		renderParam(frame1, self.model.params['refresh'], bg=bgcolors[fnum%2]).grid(row=2, column=0, columnspan=2, pady=(10,0))
		self.runButton = runButton(frame1, bgcolors[fnum%2])
		self.runButton.grid(row=2, column=2, pady=(15,0))

		for c in range(2): frame1.columnconfigure(c, weight=1)
		frame1.pack(fill='x', side='top')
		fnum += 1

		#Can't change the background color of a progress bar on Mac, so we have to put a gray stripe on top :-/
		frame0 = tk.Frame(self, padx=10, pady=0, bg=bgcolors[1])
		self.progress = progressBar(root=frame0)
		self.progress.grid(row=0, column=0)
		frame0.columnconfigure(0,weight=1)
		frame0.pack(fill='x', side='top')

		caip = self.model.doHooks('CpanelAboveItemParams', [self, bgcolors[fnum%2]])
		if caip:
			caip.pack(fill='x', side='top')
			fnum += 1

		#Per-good and per-breed parameters
		for k, param in model.params.perGood.items():
			e = renderParam(None, param, bg=bgcolors[fnum%2])
			if e is not None: e.pack(fill='x')
		if len(model.params.perGood): fnum += 1 #Only increment the stripe counter if we had any good params to draw
		for k, param in model.params.perBreed.items():
			e = renderParam(None, param, bg=bgcolors[fnum%2])
			if e is not None: e.pack(fill='x')
		if len(model.params.perBreed): fnum += 1

		cap = self.model.doHooks('CpanelAboveParams', [self, bgcolors[fnum%2]])
		if cap:
			cap.pack(fill='x', side='top')
			fnum += 1

		#Pull out grouped parameters
		groups = []
		for group in self.model.params.groups: groups += list(group.members.keys())

		#Global parameters
		for k, param in self.model.params.globals.items():
			if getattr(param, 'config', False) or k in groups: continue
			e = renderParam(self, param, bg=bgcolors[fnum%2])
			if e is not None: e.pack(fill='x')
		fnum += 1

		#Param groups
		for group in self.model.params.groups:
			group.element = expandableFrame(self, bg=bgcolors[fnum%2], padx=5, pady=10, text=group.title, fg="#333", font=font, startOpen=group.open)
			i=0
			for p in group.members.values():
				f = renderParam(group.element.subframe, p, bg=bgcolors[fnum%2])
				f.pack(fill='x')
				i += 1
			if group.element is not None: group.element.pack(fill='x')
			fnum += 1

		#Checkgrid parameters
		for p in self.model.params.values():
			if p.type!='checkgrid' or p.name=='shocks': continue
			p.element = checkGrid(parent=self, text=p.title, columns=getattr(p, 'columns', 3), bg=bgcolors[fnum%2], callback=p.setVar())
			for k,v in p.opts.items():
				if not isinstance(v, (tuple, list)): v = (v, None)
				elif len(v) < 2: v = (v[0], None)
				p.element.addCheck(k, v[0], p.vars[k], v[1])
			p.element.pack(fill='both')
			fnum += 1

		cas = self.model.doHooks('CpanelAboveShocks', [self, bgcolors[fnum%2]])
		if cas:
			cas.pack(fill='x', side='top')
			fnum += 1

		#Shock checkboxes and buttons
		if len(self.model.shocks):
			self.model.shocks.element = expandableFrame(self, text=self.model.shocks.title, padx=5, pady=8, font=font, bg=bgcolors[fnum%2])
			self.model.shocks.element.checks = {}
			self.model.params['shocks'].element = self.model.shocks.element
			for shock in self.model.shocks.shocksExceptButtons.values():
				bv = tk.BooleanVar(value=shock.selected)
				shock.element = tk.Checkbutton(self.model.shocks.element.subframe, text=shock.name, var=bv, onvalue=True, offvalue=False, bg=bgcolors[fnum%2], anchor='w', command=shock.setCallback)
				shock.element.BooleanVar = bv #To set via the shock object
				self.model.shocks.element.checks[shock.name] = bv #To set via the shock parameter
				if shock.desc is not None: Tooltip(shock.element, shock.desc)
				shock.element.pack(fill='both')

			b=0
			if len(self.model.shocks.buttons):
				bframe = tk.Frame(self.model.shocks.element.subframe, bg=bgcolors[fnum%2])
				for c in range(2): bframe.columnconfigure(c ,weight=1)
				for shock in self.model.shocks.buttons.values():
					shock.element = tk.Button(bframe, text=shock.name, command=shockCallback(shock.name), padx=10, pady=10, highlightbackground=bgcolors[fnum%2])
					shock.element.grid(row=3+int(ceil((b+1)/2)), column=b%2, sticky='w')
					if shock.desc is not None: Tooltip(shock.element, shock.desc)
					b+=1
				bframe.pack(fill='both')
			self.model.shocks.element.pack(fill='x', side='top')

		cbot = self.model.doHooks('CpanelBottom', [self, bgcolors[fnum%2]])
		if cbot:
			cbot.pack(fill='x', side='top')
			fnum += 1

	#Separate function so we can call it again when MPL tries to override
	def setAppIcon(self):
		"""Set the dock/taskbar icon to the Helipad icon."""
		try:
			__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
			icon = os.path.join(__location__, 'Helipad.png')
			pi = tk.PhotoImage(file=icon, master=self)
			self.tk.call('wm','iconphoto', self._w, pi)
		except: pass

	def cpanelClose(self):
		"""Cleanup on cpanel close so a running model will keep running."""
		for p in self.model.params.values(): p.element = None
		self.model.cpanel = None
		self.destroy()

	def step(self) -> int:
		"""Step one period at a time and update the visualization. For use in debugging."""
		t = self.model.step()
		self.model.graph.update(self.model.data.getLast(1))
		return t

#
# MISCELLANEOUS INTERFACE ELEMENTS
#

class logSlider(tk.Frame):
	"""A slider with discrete specified intervals. https://helipad.dev/functions/logslider/"""
	def __init__(self, parent=None, title=None, command=None, bg='#FFFFFF', font=('Lucida Grande',12), values=(), **kwargs):
		tk.Frame.__init__(self, parent, bg=bg)
		self.label = tk.Label(self, font=font, text=title, bg=bg).pack(side='top') if title else None
		self.values = values
		self.extCommand = command
		self.number = values[0]

		#Receives an index from the slider and sets the value
		def setText(idx):
			self.number = self.values[int(idx)]
			self.text.configure(text=self.values[int(idx)])
			if self.extCommand is not None: self.extCommand(self.values[int(idx)])

		self.slide = tk.Scale(self, command=setText,
			bg=bg, showvalue=0, from_=0, to=len(self.values)-1, font=font, **kwargs
		)
		self.text = tk.Label(self, font=font, width=4, bg=bg)
		self.slide.pack(side='right', expand=1, fill='x')
		self.text.pack(side='top', fill='both', padx=5)

	def get(self): return self.number
	def set(self, val):
		"""Receive a value and set the slider to the corresponding index."""
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

class expandableFrame(tk.Frame):
	"""A frame that can be expanded and collapsed by clicking on the title."""
	def __init__(self, parent=None, text: str='', fg='#333', bg='#FFF', padx: int=8, pady=None, font=None, startOpen=True):
		tk.Frame.__init__(self, parent, bg=bg)
		self.columnconfigure(1, weight=1)

		self.pady=pady
		self.padx=padx

		self.text = text
		self.titleLabel = tk.Label(self, fg=fg, bg=bg, font=font, cursor='hand2')
		self.titleLabel.bind('<Button-1>', self.toggle)
		self.titleLabel.grid(row=0, column=1, sticky='we', pady=(pady, 2))

		#Possibility of adding buttons on either side
		class btn(tk.Label):
			def __init__(self2, *args, **kwargs):
				self2.active = False
				self2.command = None
				hoverbg = Color(bg).darken().hex
				normalfg = Color(fg).lighten().hex
				hoverfg = Color(fg).lighten(1).hex
				super().__init__(*args, width=2, bg=bg, fg=normalfg, **kwargs)

				def hover(event):
					if self2.active: self2.config(bg=hoverbg, fg=hoverfg)
				def leave(event):
					if self2.active: self2.config(bg=bg, fg=normalfg)

				self2.bind('<Button-1>', self2.execute, add='+')
				self2.bind('<Enter>', hover, add='+')
				self2.bind('<Leave>', leave, add='+')

			def setup(self2, label, command, desc=None):
				self2.command = command
				self2.active = True
				self2.config(text=label)
				if desc: Tooltip(self2, desc)

			def execute(self2, e=None):
				if self2.active and self2.command is not None: self2.command()

		self.buttons = { 'left': btn(self), 'right': btn(self) }
		self.buttons['left'].grid(row=0, column=0, sticky='w', padx=5)
		self.buttons['right'].grid(row=0, column=2, sticky='e', padx=5)

		self.subframe = tk.Frame(self, padx=padx, pady=0, bg=bg)
		self._open = tk.IntVar()
		self.open = startOpen

	def toggle(self, event=None): self.open = not self.open

	@property
	def open(self): return bool(self._open.get())

	@open.setter
	def open(self, val):
		if val: #open
			self.subframe.grid(row=1, column=0, columnspan=3, padx=self.padx, pady=0, sticky='we')
			self.titleLabel['text'] = self.text+' '+'▾'
			self._open.set(1)
		else: #close
			self.subframe.grid_forget()
			self.titleLabel['text'] = self.text+' '+'▸'
			self._open.set(0)

class textCheck(tk.Label):
	"""A checkbox-like widget whose toggle is the entire element. `bg` and `fg` take a two-element color tuple for inactive and active states. https://helipad.dev/functions/textcheck/"""
	def __init__(self, parent=None, text=None, bg=('#FFFFFF','#419BF9'), fg=('#333333','#FFFFFF'),
		defaultValue=False, anchor='w', desc=None, callback=None
	):
		super().__init__(parent, text=text, bg=bg[defaultValue], fg=fg[defaultValue], anchor=anchor)
		self.bg = (Color(bg[0]), Color(bg[1]))
		self.fg = (Color(fg[0]), Color(fg[1]))

		#Generate disabled and hover colors
		self.disabledbg = (self.bg[0], self.bg[1].lighten(2))
		self.disabledfg = (self.fg[0].lighten(2), self.fg[1].lighten(2))
		hoverbg = (self.bg[0].darken(), self.bg[1].darken())
		hoverfg = (self.fg[0].darken(), self.fg[1].darken())

		self.value = defaultValue
		self.enabled = True

		def hover(event):
			if self.enabled: self.config(bg=hoverbg[self.value].hex, fg=hoverfg[self.value].hex)
		def leave(event):
			if self.enabled: self.config(bg=self.bg[self.value].hex, fg=self.fg[self.value].hex)

		if desc: Tooltip(self, desc)
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

class checkEntry(tk.Frame):
	"""A checkbox that enables/disables a text box. https://helipad.dev/functions/checkentry/"""
	def __init__(self, parent=None, title=None, width=20, bg='#FFFFFF', padx=0, pady=0, default='', datatype='string', command=None, limits=(0, 10**100)):
		tk.Frame.__init__(self, parent, bg=bg, padx=padx, pady=pady)
		self.callback = command

		#If we're enforcing int, don't allow nonnumerical input
		self.datatype=datatype
		def validate(code, insert, oldval, newval):
			if not self.enabled: return
			allow = True
			if self.datatype=='int' and code == '1':
				for c in insert:
					if c not in '0123456789':
						allow = False
			if allow: self.callback(int(newval) if self.datatype=='int' and newval!='' else newval)
			return allow
		valint = self.register(validate)

		self.enabled = True
		self.entryValue = tk.StringVar()
		self.entryValue.set(default)
		if datatype=='string':
			self.textbox = tk.Entry(self, textvariable=self.entryValue, width=width, state='disabled', validate='key', validatecommand=(valint, '%d', '%S', '%s', '%P'), highlightbackground=bg)
		elif datatype=='int':
			self.textbox = tk.Spinbox(self, from_=limits[0], to=limits[1], textvariable=self.entryValue, width=width, state='disabled', validate='key', validatecommand=(valint, '%d', '%S', '%s', '%P'), highlightbackground=bg)
		else: raise ValueError(ï('Invalid Checkentry datatype. Must be either "string" or "int"'))
		self.textbox.grid(row=0, column=1)

		self.checkVar = tk.BooleanVar()
		self.checkbox = tk.Checkbutton(self, text=title, bg=bg, var=self.checkVar, onvalue=True, offvalue=False, command=self.disableTextfield)
		self.checkbox.grid(row=0, column=0)

	def disableTextfield(self):
		"""Update the enabled state of the text field to correspond to the value of the checkbox. https://helipad.dev/functions/checkentry/disabletextfield/"""
		self.textbox.config(state='disabled' if not self.checkVar.get() else 'normal')
		if callable(self.callback): self.callback(self.get())

	def get(self):
		"""Retrieve the value of the combined input. Returns `False` if the checkbox is unchecked, and the value of the textbox otherwise. https://helipad.dev/functions/checkentry/get/"""
		if not self.checkVar.get(): return False
		v = self.entryValue.get()
		if self.datatype=='int':
			return 0 if v=='' else int(v)
		else: return v

	def set(self, val):
		"""Set the input value. Can receive a `bool` to toggle the checkbox, or a `string` or an `int` (depending on the datatype) to change the value of the textbox. https://helipad.dev/functions/checkentry/set/"""
		if isinstance(val, bool):
			self.checkVar.set(val)
		elif isinstance(val, (str, int)):
			if self.datatype=='int' and val!='': val=int(val)
			self.checkVar.set(True)
			self.entryValue.set(val)
		self.disableTextfield()

	def enable(self):
		"""Enable the `checkEntry` element so it can be interacted with by the user. https://helipad.dev/functions/checkentry/enable/"""
		self.disabled(False)
	def disable(self):
		"""Disable the `checkEntry` element so it cannot be interacted with by the user.https://helipad.dev/functions/checkentry/disable/"""
		self.disabled(True)
	def disabled(self, disable):
		"""Enables or disables the `checkEntry` element. https://helipad.dev/functions/checkentry/disabled/"""
		self.checkbox.config(state='disabled' if disable else 'normal')
		self.textbox.config(state='disabled' if disable or not self.checkVar.get() else 'normal')
		self.enabled = not disable

	#Here for compatibility with other Tkinter widgets
	def configure(self, state): self.disabled(state=='disabled')

class checkGrid(expandableFrame):
	"""An `expandableFrame` full of `textCheck`s, with setters and getters. https://helipad.dev/functions/checkentry/"""
	def __init__(self, parent=None, text: str='', columns: int=3, fg='#333', bg='#FFF', padx: int=8, pady: int=5, font=('Lucida Grande', 16) if sys.platform=='darwin' else ('Calibri', 14), startOpen=True, callback=None):
		super().__init__(parent=parent, text=text, fg=fg, bg=bg, padx=padx, pady=pady, font=font, startOpen=startOpen)
		self.bg = bg
		self.columns = columns
		self.checks = {}
		self._index=0
		self.callback = callback

		for i in range(columns): self.subframe.columnconfigure(i, weight=1)
		self.buttons['right'].setup('✔︎', self.toggleAll)

	def addCheck(self, var, text: str, defaultValue: bool=True, desc: bool=None):
		"""Adds a `textCheck` element to the frame. https://helipad.dev/functions/checkgrid/addcheck/"""
		if self.callback is not None:
			def cbWrap(val): self.callback((var, val))
		else: cbWrap = None

		self.checks[var] = textCheck(self.subframe, text=text, anchor='w', defaultValue=defaultValue, bg=(self.bg, '#419BF9'), desc=desc, callback=cbWrap)
		self.checks[var].grid(row=int(ceil(len(self.checks)/self.columns)), column=(len(self.checks)-1)%self.columns, sticky='we')
		return self.checks[var]

	def toggleAll(self):
		if [True for c in self.checks.values() if c.get()]:
			for c in self.checks.values(): c.set(False)
		else:
			for c in self.checks.values(): c.set(True)

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

class Tooltip:
	"""Replaces `PMW.balloon` because it's unreliably maintained. Modified from https://stackoverflow.com/questions/3221956/how-do-i-display-tooltips-in-tkinter"""
	def __init__(self, widget, text, bg='#FFFFEA', pad=(5, 3, 5, 3), waittime=500, wraplength=250, tip_delta=(10, 5)):
		for v in ['text', 'widget', 'bg', 'pad', 'waittime', 'wraplength', 'tip_delta']: setattr(self, v, locals()[v]) #Populate object with arguments
		self.widget.bind("<Enter>", self.onEnter)
		self.widget.bind("<Leave>", self.onLeave)
		self.widget.bind("<ButtonPress>", self.onLeave)
		self.id = None
		self.tw = None

	def onLeave(self, event=None):
		self.unschedule()
		self.hide()

	def onEnter(self, event=None):
		self.unschedule()
		self.id = self.widget.after(self.waittime, self.show)

	def unschedule(self):
		id_ = self.id
		self.id = None
		if id_: self.widget.after_cancel(id_)

	def show(self):
		self.tw = tk.Toplevel(self.widget) # creates a toplevel window
		self.tw.wm_overrideredirect(True) # Leaves only the label and removes the app window

		win = tk.Frame(self.tw, background=self.bg, borderwidth=0)
		label = tk.Label(win, text=self.text, justify='left', background=self.bg, relief='solid', borderwidth=0, wraplength=self.wraplength)
		label.grid(padx=(self.pad[0], self.pad[2]), pady=(self.pad[1], self.pad[3]), sticky='nsew')
		win.grid()

		#Calculate tooltip position
		s_width, s_height = self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()
		width, height = (self.pad[0] + label.winfo_reqwidth() + self.pad[2], self.pad[1] + label.winfo_reqheight() + self.pad[3])
		mouse_x, mouse_y = self.widget.winfo_pointerxy()
		x1, y1 = mouse_x + self.tip_delta[0], mouse_y + self.tip_delta[1]
		x2, y2 = x1 + width, y1 + height

		x_delta = max(x2 - s_width, 0)
		y_delta = max(y2 - s_height, 0)

		#If offscreen
		if (x_delta, y_delta) != (0, 0):
			if x_delta: x1 = mouse_x - self.tip_delta[0] - width
			if y_delta: y1 = mouse_y - self.tip_delta[1] - height
		y1 = max(y1, 0)

		self.tw.wm_geometry(f'+{x1}+{y1}')

	def hide(self):
		if self.tw: self.tw.destroy()
		self.tw = None