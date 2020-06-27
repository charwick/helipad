# ==========
# Classes to abstract the interface between model parameters and GUI elements.
# Do not run this file; import model.py and run from your file.
# ==========

from helipad.helpers import *

#In the absence of Tkinter, minimal replacements
if isIpy():
	class StringVar:
		def __init__(self): self.val=None
		def get(self): return self.val
		def set(self, val): self.val = val
	BooleanVar = StringVar
else:
	from tkinter import StringVar, BooleanVar

class Param(Item):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.reset() #Populate with default values
	
	#Set values from defaults
	#Global generic:				int → int
	#Per-breed universal generic:	int → dict{int}
	#Per-breed specific generic:	dict{int} → dict{int}
	def reset(self):
		if self.obj is None: self.value = self.default
		else:
			if isinstance(self.default, dict):
				self.value = {k:self.default[k] if k in self.default else 0 for k in self.keys}
			else:
				self.value = {k:self.default for k in self.keys}
	
	#Common code for the set methods
	def setParent(self, val, item=None, updateGUI=True):
		if self.obj is not None and item is None: raise KeyError('A '+self.obj+' whose parameter value to set must be specified')
		
		#Jupyter requires an explicit update for all parameter types.
		if updateGUI and isIpy():
			if self.obj is None: self.element.children[0].value = val
			else: self.element[item].children[0].value = val
	
	#A generic set method to be overridden
	def set(self, val, item=None, updateGUI=True):
		self.setParent(val, item, updateGUI)
		if self.obj is None: self.value = val
		else: self.value[item] = val
	
	def get(self, item=None):
		return self.value if self.obj is None or item is None else self.value[item]
	
	#Returns a one-parameter setter since Jupyter needs it
	def setf(self, item=None):
		def set(val):
			self.set(val, item, updateGUI=False)
		return set
	
	@property
	def range(self): return None
	
	#If a breed or good gets added after the parameter instantiation, we want to be able to keep up
	def addKey(self, key):
		if self.obj is None: print('Can\'t add keys to a global parameter…')
		elif not isinstance(self.default, dict):
			self.value[key] = self.default
		elif key in self.default:
			self.value[key] = self.default[key]	#Forgive out-of-order specification
		else: return True

class MenuParam(Param):
	def __init__(self, **kwargs):
		#Instantiate the objects once, because we don't want to overwrite them
		self.value = StringVar() if kwargs['obj'] is None else {b:StringVar() for b in kwargs['keys']}
		super().__init__(**kwargs)
		
	#Set values from defaults
	#Global menu:					str → StringVar
	#Per-breed universal menu:		str → dict{StringVar}
	#Per-breed specific menu:		dict{str} → dict{StringVar}
	def reset(self):
		if self.obj is None: self.value.set(self.opts[self.default])
		else:
			if isinstance(self.default, dict):
				for k,v in self.value.items():
					if k in self.default: v.set(self.opts[self.default[k]])
				for b in self.keys:
					if not b in self.default: self.value[b].set('') #Make sure we've got all the items in the array
			else:
				#Set to opts[self.default] rather than self.default because OptionMenu deals in the whole string
				for k,v in self.value.items(): v.set(self.opts[self.default])
	
	def set(self, val, item=None, updateGUI=True):
		self.setParent(val, item, updateGUI)
		if self.obj is None: self.value.set(self.opts[val])
		else: self.value[item].set(self.opts[val])
	
	def get(self, item=None):
		#Flip the k/v of the options dict and return the slug from the full text returned by the menu variable
		flip = {y:x for x,y in self.opts.items()}
		if self.obj is None: return flip[self.value.get()]								#Global parameter
		else:
			if item is None: return {o:flip[v.get()] for o,v in self.value.items()}		#Item parameter, item unspecified
			else: return flip[self.value[item].get()]									#Item parameter, item specified
	
	@property
	def range(self): return self.opts.keys()
	
	def addKey(self, key):
		if super().addkey(key) is None: return
		self.value[key] = StringVar()
		self.value[key].set(self.opts[next(iter(self.opts))])	#Choose first item of the list
			

class CheckParam(Param):
	def __init__(self, **kwargs):
		#Instantiate the objects once, because we don't want to overwrite them
		self.value = BooleanVar() if kwargs['obj'] is None else {b:BooleanVar() for b in kwargs['keys']}
		super().__init__(**kwargs)
	
	#Set values from defaults
	#Global check:					bool → BooleanVar
	#Per-breed universal check:		bool → dict{BooleanVar}
	#Per-breed specific check:		dict{bool} → dict{BooleanVar}
	def reset(self):
		if self.obj is None: self.value.set(self.default)
		else:
			if isinstance(self.default, dict):
				for k,v in self.value.items():
					if k in self.default: v.set(self.default[k])
				for b in self.keys:
					if not b in self.value: self.value[b].set(False) #Make sure we've got all the breeds in the array
			else:
				for k in self.value: self.value[k].set(self.default)
	
	def set(self, val, item=None, updateGUI=True):
		self.setParent(val, item, updateGUI)
		if self.obj is None: self.value.set(val)
		else: self.value[item].set(val)
	
	def get(self, item=None):
		return self.value.get() if self.obj is None or item is None else self.value[item].get()
	
	@property
	def range(self): return [False, True]
	
	def addKey(self, key):
		if super().addkey(key) is None: return
		self.value[key] = BooleanVar()

class SliderParam(Param):
	
	#Because the slider tkinter widget doesn't use a Var() object like the others, we have
	#to explicitly push the value to the slider if necessary
	def set(self, val, item=None, updateGUI=True):
		self.setParent(val, item, updateGUI)
		if self.obj is None:
			self.value = val
			if updateGUI and hasattr(self, 'element') and not isIpy():
				self.element.set(val)
		else:
			self.value[item] = val
			if updateGUI and hasattr(self, 'element') and not isIpy():
				self.element[item].set(val)
	
	def get(self, item=None):
		v = super().get(item)
		#Have sliders with an int step value return an int
		if self.opts is not None and 'step' in self.opts and isinstance(self.opts['step'], int):
			if isinstance(v, dict): v = {k: int(val) for k,val in v.items()}
			else: v = int(v)
		return v
	
	@property
	def range(self):
		values = arange(self.opts['low'], self.opts['high'], self.opts['step']).tolist()
		values.append(self.opts['high']) #arange doesn't include the high
		return values
	
	def addKey(self, key):
		if super().addkey(key) is None: return
		self.value[key] = 0