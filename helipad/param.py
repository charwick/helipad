"""
Classes to abstract the interface between model parameters and GUI elements. This module should not be imported directly; use `model.params.add()` instead.
"""

from itertools import combinations
import warnings
from helipad.helpers import *
from numpy import arange, random

class Param(Item):
	"""Base class defining a model parameter that can be set before or during runtime. https://helipad.dev/functions/param/"""
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		if not hasattr(self, 'per'): self.per=None
		if not hasattr(self, 'value'): self.value = {b:self.defaultVal for b in kwargs['pKeys']} if self.per else self.defaultVal
		self.element = None
		self.reset() #Populate with default values

	def __repr__(self): return f'<{self.__class__.__name__}: {self.name}>'

	#Global generic:				int → int
	#Per-breed universal generic:	int → dict{int}
	#Per-breed specific generic:	dict{int} → dict{int}
	def reset(self):
		"""Reset the parameter to its default value. https://helipad.dev/functions/param/reset/"""
		if self.per is None: self.setSpecific(self.default)
		else:
			if isinstance(self.default, dict):
				for i in self.pKeys:
					self.setSpecific(self.default[i] if i in self.default else self.defaultVal, i)
			else:
				for i in self.pKeys: self.setSpecific(self.default, i)

	def setParent(self, val, item=None, updateGUI: bool=True):
		"""Common code for subclasses' `set()` methods."""
		if self.per is not None and item is None: raise KeyError(ï('A {} whose parameter value to set must be specified.').format(self.per))

		#Jupyter requires an explicit update for all parameter types.
		if updateGUI and isNotebook() and self.element is not None:
			if self.per is None: self.element.children[0].value = val
			else: self.elements[item].children[0].value = val

	#Don't override this one
	def set(self, val, item=None, updateGUI: bool=True):
		"""Set the value of the parameter to `val`. Do not call directly; use `model.param()` instead. https://helipad.dev/functions/param/set/"""
		if getattr(self, 'setter', False):
			val = self.setter(val, item)
			if val is not None: self.setSpecific(val, item)
		else: self.setSpecific(val, item, updateGUI)

	def setSpecific(self, val, item=None, updateGUI: bool=True):
		"""A generic set method to be overridden by subclasses."""
		self.setParent(val, item, updateGUI)
		if self.per is None: self.value = val
		else: self.value[item] = val

	#Don't override this one
	def get(self, item=None):
		"""Retrieve the value of the parameter. Do not call directly; use `model.param()` instead. https://helipad.dev/functions/param/get/"""
		if getattr(self, 'getter', False):
			v = self.getter(item)
			if v is not None: return v #Allow passing to the default getter
		return self.getSpecific(item)

	def getSpecific(self, item=None):
		"""A generic get method to be overridden by subclasses."""
		return self.value if self.per is None or item is None else self.value[item]

	def disabled(self, disable: bool):
		"""Enables or disables the parameter's GUI element. https://helipad.dev/functions/param/disabled/"""
		if self.element is None: return
		for e in ([self.element] if self.per is None else self.elements.values()):
			if isNotebook():
				for i in e.children: i.disabled = disable
			else:
				e.configure(state='disabled' if disable else 'normal')

	def disable(self):
		"""Disables the parameter's control panel GUI element so that it cannot be interacted with or changed by the user. https://helipad.dev/functions/param/disable/"""
		self.disabled(True)
	def enable(self):
		"""Enables the parameter's control panel GUI element so that it can be interacted with by the user. https://helipad.dev/functions/param/enable/"""
		self.disabled(False)

	@property
	def range(self):
		"""A list of possible values that the parameter can take."""
		return None

	#If a breed or good gets added after the parameter instantiation, we want to be able to keep up
	def addKey(self, key: str):
		"""Update a per-item parameter with a new item and assign it the default value specified at the `Param` object's instantiation. https://helipad.dev/functions/param/addkey/"""
		if self.per is None: warnings.warn(ï('Can\'t add keys to a global parameter…'), None, 2)
		elif not isinstance(self.default, dict):
			self.value[key] = self.default
		elif key in self.default:
			self.value[key] = self.default[key]	#Forgive out-of-order specification
		else: return True

	@property
	def defaultVal(self):
		"""Fallback value in case `param.default` is not specified on init."""
		return None

class MenuParam(Param):
	"""A parameter type that takes discrete string values. https://helipad.dev/functions/param/"""
	type = 'menu'

	def setParent(self, val, item=None, updateGUI=True):
		if self.per is not None and item is None: raise KeyError(ï('A {} whose parameter value to set must be specified.').format(self.per))
		if updateGUI and not isNotebook() and self.element is not None:
			sv = self.element if self.per is None else self.elements[item]
			sv.StringVar.set(self.opts[val]) #Saved the StringVar here
		else: super().setParent(val, item, updateGUI)

	@property
	def range(self): return self.opts.keys()

	#Choose first item of the list
	@property
	def defaultVal(self): return next(iter(self.opts))

class CheckParam(Param):
	"""A parameter type that takes a boolean value. https://helipad.dev/functions/param/"""
	defaultVal = False
	type='check'

	def setParent(self, val: bool, item=None, updateGUI: bool=True):
		if self.per is not None and item is None: raise KeyError(ï('A {} whose parameter value to set must be specified.').format(self.per))
		if updateGUI and not isNotebook() and self.element is not None:
			sv = self.element if self.per is None else self.elements[item]
			sv.BooleanVar.set(val) #Saved the BooleanVar here
		else: super().setParent(val, item, updateGUI)

	@property
	def range(self): return [False, True]

class SliderParam(Param):
	"""A parameter type that takes numerical values. https://helipad.dev/functions/param/"""
	type='slider'

	def setSpecific(self, val, item=None, updateGUI: bool=True):
		#If we're receiving a value from a Jupyter logslider, it's an index and not a value
		if not updateGUI and isNotebook() and isinstance(self.opts, list): val = self.opts[val]

		self.setParent(val, item, updateGUI)
		super().setSpecific(val, item, updateGUI)

		#Because the slider tkinter widget doesn't use a Var() object like the others, we have
		#to explicitly push the value to the slider if necessary
		if updateGUI and self.element is not None and not isNotebook():
			if self.per is None: self.element.set(val)
			else: self.elements[item].set(val)

	def getSpecific(self, item=None):
		v = super().getSpecific(item)
		#Have sliders with an int step value return an int
		if self.opts is not None and 'step' in self.opts and isinstance(self.opts['step'], int):
			if isinstance(v, dict): v = {k: int(val) for k,val in v.items()}
			else: v = int(v)
		return v

	@property
	def range(self) -> list:
		values = arange(self.opts['low'], self.opts['high'], self.opts['step']).tolist()
		values.append(self.opts['high']) #arange doesn't include the high
		return values

	def addKey(self, key: str):
		if super().addKey(key) is None: return
		self.value[key] = 0

	@property
	def defaultVal(self): return self.opts['low'] if isinstance(self.opts, dict) else self.opts[0]

	#Override in order to update log slider
	def setParent(self, val, item=None, updateGUI: bool=True):
		if self.per is not None and item is None: raise KeyError(ï('A {} whose parameter value to set must be specified.').format(self.per))

		if isNotebook() and self.element is not None and (self.per is None or item in self.elements):
			el = self.element if self.per is None else self.elements[item]

			#Regular slider update
			if updateGUI and isinstance(self.opts, dict): el.children[0].value = val

			#If it's a log slider in Jupyter, update the label, even if we're receiving from the GUI
			#And then push to the slider if we're not receiving from the GUI
			elif isinstance(self.opts, list):
				el.children[1].value = str(val)
				if updateGUI and val in self.opts: el.children[0].value = self.opts.index(val)

class CheckentryParam(Param):
	"""A parameter type that takes `False` if unchecked, or a string value if checked. https://helipad.dev/functions/param/"""
	defaultVal = ''
	type='checkentry'

	def __init__(self, **kwargs):
		self.bvar = True if 'per' not in kwargs or kwargs['per'] is None else {k:True for k in kwargs['pKeys']}
		self.svar = self.defaultVal if 'per' not in kwargs or kwargs['per'] is None else {k:self.defaultVal for k in kwargs['pKeys']}
		self.value = None
		self.event = False
		kwargs['entryType'] = int if 'entryType' in kwargs and kwargs['entryType']=='int' else str
		super().__init__(**kwargs)

	def getSpecific(self, item=None):
		#Global parameter
		if self.per is None:
			if self.name=='stopafter' and self.event: return self.svar
			elif self.element is not None and not isNotebook(): return self.element.get()
			else: return self.svar if self.bvar else False
		#Per-item parameter, get all
		elif item is None:
			if hasattr(self, 'elements') and not isNotebook(): return {k: v.get() for k,v in self.elements.items()}
			else: return {k: self.svar[k] if self.bvar[k] else False for k in self.pKeys}
		#Per-item parameter, get one
		else:
			if hasattr(self, 'elements') and item in self.elements and not isNotebook(): return self.elements[item].get()
			else: return self.svar[item] if self.bvar[item] else False

	def setSpecific(self, val, item=None, updateGUI: bool=True):
		self.setParent(val, item, False) #Don't update the GUI because it's a complex multivar type
		if self.per is None:

			#Manage setting stopafter to an event
			if self.name == 'stopafter':
				if val and isinstance(val, str):
					self.event = True
					if self.element is not None:
						self.disable()
						if isNotebook():
							self.element.children[1].value = 'Event: '+val
							self.element.children[0].value = True
							self.element.add_class('helipad_checkentry_func')
						else:
							self.element.entryValue.set('Event: '+val)
							self.element.checkVar.set(True)
							self.element.textbox.config(font=('Helvetica Neue', 12,'italic')) #Lucida doesn't have an italic?
					self.svar = val
					self.bvar = True
					return
				elif self.event and self.element is not None:
					self.event = False
					if isNotebook():
						if isinstance(val, bool): self.element.children[1].value = ''
						self.element.children[0].disabled = False
						self.element.remove_class('helipad_checkentry_func')
					else:
						if isinstance(val, bool): self.element.entryValue.set('')
						self.element.enable()
						self.element.textbox.config(font=('Lucida Grande', 12))

			if self.element is not None and not isNotebook(): self.element.set(val)
			elif isinstance(val, bool):
				self.bvar = val
				if isNotebook() and self.element is not None: self.element.children[1].disabled = not val
			elif isinstance(val, self.entryType):
				self.bvar = True
				self.svar = val
				if isNotebook() and self.element is not None: self.element.children[1].disabled = False
		else:
			if hasattr(self, 'elements') and not isNotebook(): self.elements[item].set(val)
			elif isinstance(val, bool): self.bvar[item] = val
			elif isinstance(val, self.entryType):
				self.bvar[item] = True
				self.svar[item] = val

		if updateGUI and isNotebook() and self.element is not None:
			els = self.element.children if self.per is None else self.elements[item].children
			els[0].value = val is not False
			if not isinstance(val, bool): els[1].value = str(val) #Ipy text widget requires a string

	#Only re-enable the textbox if the checkbox is checked
	def disabled(self, disable):
		if self.element is not None and isNotebook() and not disable:
			for e in ([self.element] if self.per is None else self.elements.values()):
				e.children[0].disabled = False
				if e.children[0].value: e.children[1].disabled = False
		else: super().disabled(disable)

class CheckgridParam(Param):
	"""A parameter type that takes a list of boolean values. https://helipad.dev/functions/param/"""
	defaultVal = []
	type='checkgrid'

	def __init__(self, **kwargs):
		if kwargs['per'] is not None: raise ValueError(ï('Cannot instantiate per-item checkgrid parameter.'))
		if 'default' not in kwargs or not isinstance(kwargs['default'], list): kwargs['default'] = []
		if isinstance(kwargs['opts'], list): kwargs['opts'] = {k:k for k in kwargs['opts']}
		for k,v in kwargs['opts'].items():
			if isinstance(v, str): kwargs['opts'][k] = (v, None) #Standardized key:(name, tooltip) format
		self.vars = {k: k in kwargs['default'] for k in kwargs['opts']}
		super().__init__(**kwargs)

	@property
	def pKeys(self) -> list: return list(self.vars.keys())

	def getSpecific(self, item=None):
		useElement = self.element is not None and not isNotebook() and not isinstance(self, Shocks)
		vals = self.element if useElement else self.vars
		if item is not None: return vals[item]
		else: return [k for k,v in vals.items() if (v.get() if useElement else v)]

	def set(self, item, val=True, updateGUI: bool=True):
		if getattr(self, 'setter', False):
			val = self.setter(val, item)
			if val is not None: self.setSpecific(item, val)
		else: self.setSpecific(item, val, updateGUI)

	#Takes a list of strings, or a key-bool pair
	def setSpecific(self, item, val=True, updateGUI: bool=True):
		if isinstance(item, list):
			for i in self.pKeys: self.set(i, i in item)
		else:
			if self.element is not None and not isNotebook(): self.element.checks[item].set(val)
			self.vars[item] = val

			if updateGUI and isNotebook() and hasattr(self, 'elements'):
				try: self.elements[item].children[0].value = val
				except KeyError: return #Ipywidgets ≥8.0 runs the callback on instantiation before the element property is set

	@property
	def range(self) -> list:
		combos = []
		for i in range(len(self.vars)): combos += list(combinations(self.pKeys, i+1))
		return combos

	def disabled(self, disable: bool):
		if hasattr(self, 'elements') and isNotebook():
			for e in self.elements.values():
				if hasattr(e, 'children'): e.children[0].disabled = disable
		else: super().disabled(disable)

	def addItem(self, name: str, label: str, position=None, selected: bool=False):
		"""Add a new checkbox to the grid."""
		if self.element is not None and not isNotebook(): raise RuntimeError(ï('Cannot add checkgrid items after control panel is drawn.'))

		if position is None or position > len(self.vars): self.opts[name] = label
		else:		#Reconstruct opts because there's no insert method
			newopts, i = ({}, 1)
			for k,v in self.opts.items():
				if position==i: newopts[name] = label
				newopts[k] = v
				i+=1
			self.opts = newopts

		#Refresh
		if getattr(self, 'containerElement', False):
			from ipywidgets import interactive
			self.elements[name] = interactive(self.setVar(name), val=selected)
			self.elements[name].children[0].description = label
			if position is None or position > len(self.vars): self.containerElement.children += (self.elements[name],)
			else: self.containerElement.children = self.containerElement.children[:position-1] + (self.elements[name],) + self.containerElement.children[position-1:]

		self.vars[name] = selected
		if selected: self.default.append(name)

class ParamGroup:
	"""Define a collapsible group of parameters for display in the control panel. https://helipad.dev/functions/params/group/"""
	def __init__(self, name: str, members, opened: bool):
		self.title = name
		self.members = members
		self.element = None
		self.open = opened

		for p in members.values():
			if p.per is not None or p.type=='checkgrid': raise TypeError(ï('Cannot add checkgrids or per-item parameters to groups.'))
			p.group = name

	def get(self) -> dict:
		"""A `dict` with values for all parameters in the group."""
		return {name: p.get() for name, p in self.members.items()}

	def toggle(self):
		"""Open or close the frame around the grouped parameters."""
		self.open = not self.open

	@property
	def open(self) -> bool:
		"""Whether the frame around the grouped parameters is currently open."""
		return self._open

	@open.setter
	def open(self, val: bool):
		self._open = val
		if self.element is not None:
			if isNotebook(): self.element.selected_index = 0 if val else None
			else: self.element.open = val

#==================
# CONTAINER CLASSES
#==================

class fStoreWithInterface(funcStore):
	"""Subclass of `FuncStore` that also deletes parameter interface elements on removal. https://helipad.dev/functions/funcstore/"""
	def remove(self, name: str):
		if isinstance(name, (list, tuple)): return [self.remove(n) for n in name]

		if name not in self: return False
		if getattr(self[name], 'config', False): raise ValueError(ï('Cannot remove built-in parameters.'))
		self._destroy(self[name])

		del self[name]
		return True

	def _destroy(self, item):
		if item.element:
			if not isNotebook(): item.element.forget()
			else: item.element.close()

class Params(fStoreWithInterface):
	"""Interface for storing, adding, and accessing model parameters. Stored in `model.params`. https://helipad.dev/functions/params/"""
	multi = False

	def __init__(self, model):
		super().__init__()
		self.model = model
		self.groups = []

	def add(self, name: str, title: str, type: str, dflt, opts={}, runtime: bool=True, callback=None, per=None, desc=None, prim=None, getter=None, setter=None, **args):
		"""Register a global parameter to be displayed in the control panel. `type` can take `'menu'`, `'check'`, `'slider'`, `'checkentry'`, `'checkgrid'`, or `'hidden'`, and `opts` will depend on the parameter type. https://helipad.dev/functions/params/add/"""
		if name in self: warnings.warn(ï('Parameter \'{}\' already defined. Overriding…').format(name), None, 2)

		if callable(getter):
			args['getter'] = lambda item=None: getter(*([name, self.model] if per is None else [name, self.model, item]))

		if callable(setter):
			args['setter'] = lambda val, item=None: setter(*([val, name, self.model] if per is None else [val, name, self.model, item]))

		args.update({
			'name': name,
			'title': title,
			'default': dflt,
			'opts': opts,
			'runtime': runtime,
			'callback': callback,
			'desc': desc,
			'per': per
		})
		if per is not None:
			if per=='breed':
				if prim is None:
					if len(list(self.model.agents.keys()))==1: prim = next(iter(self.model.agents.keys()))
					else: raise KeyError(ï('Per-breed parameter must specify which primitive it belongs to.'))
				args['prim'] = prim
			args['pKeys'] = self.model.agents[prim].breeds if per=='breed' else self.model.goods

		if type.title()+'Param' in globals(): pclass = globals()[type.title()+'Param']
		else:
			pclass = Param
			args['type'] = type
		self[name] = pclass(**args)
		if self.model.cpanel and isNotebook(): self.model.cpanel.__init__(self, redraw=True) #Redraw if necessary
		return self[name]

	def group(self, name: str, params: list, opened: bool=True):
		"""Group parameters into a collapsible section in the control panel. https://helipad.dev/functions/params/group/"""
		pg = ParamGroup(name, {p: self[p] for p in params}, opened)
		self.groups.append(pg)
		return pg

	#Save the configuration parameters
	def clear(self):
		"""Clear all user-added parameters and removes them from the control panel if drawn. https://helipad.dev/functions/params/clear/"""
		for p in self.values():
			if getattr(p, 'config', False): continue
			self._destroy(p)
		configs = {k:v for k,v in self.items() if getattr(v, 'config', False)}
		super().clear()
		self.update(configs)

	@property
	def globals(self):
		"""The subset of global parameters, i.e. those added with `per=None`. https://helipad.dev/functions/params/#globals"""
		return {k:v for k,v in self.items() if v.per is None}

	@property
	def perBreed(self):
		"""The subset of per-breed parameters, i.e. those added with `per='breed'`. https://helipad.dev/functions/params/#perbreed"""
		return {k:v for k,v in self.items() if v.per=='breed'}

	@property
	def perGood(self):
		"""The subset of per-good parameters, i.e. those added with `per='good'`. https://helipad.dev/functions/params/#pergood"""
		return {k:v for k,v in self.items() if v.per=='good'}

class Shocks(CheckgridParam, fStoreWithInterface):
	"""Interface for adding, storing, and executing model shocks. Stored in `model.shocks`, but also subclasses `CheckgridParam` and the same object is also located in `model.params['shocks']`. https://helipad.dev/functions/shocks/"""
	multi: bool = False

	def __init__(self, model):
		dict.__init__(self)
		CheckgridParam.__init__(self, name='shocks', title=ï('Shocks'), type='checkgrid', opts={}, dflt={}, runtime=True, config=True, per=None)
		self.model = model

		class Shock(Item):
			"""Container defining a shock to a parameter that can execute during model runtime. https://helipad.dev/functions/shock/"""
			@property
			def selected(self2) -> bool: return self.get(self2.name)

			@selected.setter
			def selected(self2, val: bool): self2.active(val)

			def active(self2, val: bool, updateGUI: bool=True):
				self.set(self2.name, bool(val))
				if updateGUI and not isNotebook() and self2.element is not None:
					self2.element.BooleanVar.set(val)

			def do(self, model):
				if self.param is not None:
					newval = self.valFunc(self.param.get(self.item))	#Pass in current value
					self.param.set(newval, self.item)
					if hasattr(self.param, 'callback') and callable(self.param.callback):
						if self.param.per is not None and self.item is not None:
							self.param.callback(model, self.param.name, self.item, newval)
						else:
							self.param.callback(model, self.param.name, newval)
				else:
					self.valFunc(model)

			#Updates the parameter value when the GUI element is clicked
			#Can't do the regular setVar without a unified Tkinter element (like CheckGrid) to route the values
			def setCallback(self, val=None):
				if not isNotebook(): val = self.element.BooleanVar.get()
				self.active(val, False)

				if callable(model.params['shocks'].callback): model.params['shocks'].callback(model, 'shocks', (self.name, val))
		self.Shock = Shock

	def __repr__(self): return f'<{self.__class__.__name__}: {len(self)} shocks>'

	def add(self, name: str, param, valFunc, timerFunc, active: bool=True, desc=None):
		"""Register a shock to parameter `param`. `valFunc` takes the current value and returns a new value. `timerFunc` is a function that takes the current model time and returns `bool` (or the string `'button'`, in which case the value is shocked when a control panel button is pressed); `valFunc` will execute whenever `timerFunc` returns `True`. `param` can also be set to `None`, in which case `valFunc` receives the model object. https://helipad.dev/functions/shocks/add/"""
		if param is not None:
			item = param[2] if isinstance(param, tuple) and len(param)>2 else None	#The good or breed whose parameter to shock
			param = self.model.params[param[0]] if isinstance(param, tuple) else self.model.params[param]
		else: item=None

		super().add(name, self.Shock(
			name=name,
			desc=desc,
			param=param,
			item=item,
			valFunc=valFunc,
			timerFunc=timerFunc,
			element=None,
			selected=active
		))

		if timerFunc != 'button': self.addItem(name, name, selected=active)

	def clear(self):
		"""Clear all registered shocks and removes the element from the control panel."""
		if self.element is not None: self._destroy(self)
		super().clear()

	def step(self):
		"""Run through the `timerFunc`s of the registered shocks and execute the `valFunc` for any `timerFunc` that returns `True`. https://helipad.dev/functions/shocks/step/"""
		for shock in self.values():
			if shock.selected and callable(shock.timerFunc) and shock.timerFunc(self.model.t):
				shock.do(self.model)

	@property
	def buttons(self):
		"""The subset of registered shocks where `shock.timerFunc=='button'` and therefore render as buttons in the control panel. https://helipad.dev/functions/shocks/#buttons"""
		return {k:s for k,s in self.items() if s.timerFunc=='button'}

	@property
	def shocksExceptButtons(self):
		"""The subset of registered shocks where `shock.timerFunc` is a function and therefore render as checkboxes in the control panel. https://helipad.dev/functions/shocks/#shocksExceptButtons"""
		return {k:s for k,s in self.items() if callable(s.timerFunc)}

	# ===============
	# TIMER FUNCTIONS
	# The following *return* timer functions; they are not themselves timer functions.
	# ===============

	def randn(self, n):
		"""Generate a timer function that returns `True` with `n`% probability each period. https://helipad.dev/functions/shocks/randn/"""
		if n<0 or n>100: raise ValueError(ï('randn() argument must be between 0 and 100.'))
		def fn(t): return random.randint(0,100) < n
		return fn

	def atperiod(self, n):
		"""Generate a timer function that returns `True` at one or several specified periods. https://helipad.dev/functions/shocks/atperiod/"""
		def fn(t):
			if isinstance(n, list): return t in n
			else: return t==n
		return fn

	def everyn(self, n: int, offset: int=0):
		"""Generates a timer function that returns `True` every `n` periods. https://helipad.dev/functions/shocks/everyn/"""
		def fn(t): return t%n-offset==0
		return fn