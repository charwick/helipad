# ==========
# Classes to abstract the interface between model parameters and GUI elements.
# Do not run this file; import model.py and run from your file.
# ==========

from helipad.helpers import *

#In the absence of Tkinter, minimal replacements
if isIpy():
	class StringVar:
		def __init__(self, value=None): self.val=value
		def get(self): return self.val
		def set(self, val): self.val = val
	BooleanVar = StringVar
else:
	from tkinter import StringVar, BooleanVar

class Param(Item):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		if not hasattr(self, 'obj'): self.obj=None
		if self.obj and not hasattr(self, 'value'): self.value = {b:self.defaultVal for b in kwargs['keys']}
		self.reset() #Populate with default values
	
	#Set values from defaults
	#Global generic:				int → int
	#Per-breed universal generic:	int → dict{int}
	#Per-breed specific generic:	dict{int} → dict{int}
	def reset(self):
		if self.obj is None: self.set(self.default)
		else:
			if isinstance(self.default, dict):
				for i in self.keys:
					self.set(self.default[i] if i in self.default else self.defaultVal, i)
			else:
				for i in self.keys: self.set(self.default, i)
	
	#Common code for the set methods
	def setParent(self, val, item=None, updateGUI=True):
		if self.obj is not None and item is None: raise KeyError('A '+self.obj+' whose parameter value to set must be specified')
		
		#Jupyter requires an explicit update for all parameter types.
		if updateGUI and isIpy() and hasattr(self, 'element'):
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
	
	#If there's no user-specified default value, this is what gets returned
	@property
	def defaultVal(self): return None

class MenuParam(Param):
	type = 'menu'
	
	def __init__(self, **kwargs):
		#Instantiate the objects once, because we don't want to overwrite them
		self.value = StringVar() if 'obj' not in kwargs or kwargs['obj'] is None else {b:StringVar() for b in kwargs['keys']}
		super().__init__(**kwargs)
	
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
		self.value[key].set(self.opts[self.defaultVal])
	
	#Choose first item of the list
	@property
	def defaultVal(self): return next(iter(self.opts))

class CheckParam(Param):
	defaultVal = False
	type='check'
	
	def __init__(self, **kwargs):
		#Instantiate the objects once, because we don't want to overwrite them
		self.value = BooleanVar() if 'obj' not in kwargs or kwargs['obj'] is None else {b:BooleanVar() for b in kwargs['keys']}
		super().__init__(**kwargs)
	
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
	type='slider'
	
	def set(self, val, item=None, updateGUI=True):
		#If we're receiving a value from a Jupyter logslider, it's an index and not a value
		if not updateGUI and isIpy() and isinstance(self.opts, list): val = self.opts[val]
		
		self.setParent(val, item, updateGUI)
		super().set(val, item, updateGUI)
		
		#Because the slider tkinter widget doesn't use a Var() object like the others, we have
		#to explicitly push the value to the slider if necessary
		if updateGUI and hasattr(self, 'element') and not isIpy():
			if self.obj is None: self.element.set(val)
			else: self.element[item].set(val)
	
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
	
	@property
	def defaultVal(self): return self.opts['low'] if isinstance(self.opts, dict) else self.opts[0]
	
	#Override in order to update log slider
	def setParent(self, val, item=None, updateGUI=True):
		if self.obj is not None and item is None: raise KeyError('A '+self.obj+' whose parameter value to set must be specified')
		
		if isIpy() and hasattr(self, 'element') and (self.obj is None or item in self.element):
			el = self.element if self.obj is None else self.element[item]
			
			#Regular slider update
			if updateGUI and isinstance(self.opts, dict): el.children[0].value = val
		
			#If it's a log slider in Jupyter, update the label, even if we're receiving from the GUI
			#And then push to the slider if we're not receiving from the GUI
			elif isinstance(self.opts, list):
				el.children[1].value = str(val)
				if updateGUI and val in self.opts: el.children[0].value = self.opts.index(val)
	
class CheckentryParam(Param):
	defaultVal = ''
	type='checkentry'
	
	def __init__(self, **kwargs):
		self.bvar = True if 'obj' not in kwargs or kwargs['obj'] is None else {k:True for k in kwargs['keys']}
		self.svar = self.defaultVal if 'obj' not in kwargs or kwargs['obj'] is None else {k:self.defaultVal for k in kwargs['keys']}
		self.value = None
		kwargs['entryType'] = int if 'entryType' in kwargs and kwargs['entryType']=='int' else str
		super().__init__(**kwargs)
	
	def get(self, item=None):
		#Global parameter
		if self.obj is None:
			if hasattr(self, 'element') and not isIpy(): return self.element.get()
			else: return self.svar if self.bvar else False
		#Per-item parameter, get all
		elif item is None:
			if hasattr(self, 'element') and not isIpy(): return {k: v.get() for k,v in self.element.items()}
			else: return {k: self.svar[k] if self.bvar[k] else False for k in self.keys}
		#Per-item parameter, get one
		else:
			if hasattr(self, 'element') and item in self.element and not isIpy(): return self.element[item].get()
			else: return self.svar[item] if self.bvar[item] else False
	
	def set(self, val, item=None, updateGUI=True):
		self.setParent(val, item, False) #Don't update the GUI because it's a complex multivar type
		if self.obj is None:
			if hasattr(self, 'element') and not isIpy(): self.element.set(val)
			elif isinstance(val, bool):
				self.bvar = val
				if isIpy() and hasattr(self, 'element'): self.element.children[1].disabled = not val
			elif isinstance(val, self.entryType):
				self.bvar = True
				self.svar = val
				if isIpy() and hasattr(self, 'element'): self.element.children[1].disabled = False
		else:
			if hasattr(self, 'element') and not isIpy(): self.element[item].set(val)
			elif isinstance(val, bool): self.bvar[item] = val
			elif isinstance(val, self.entryType):
				self.bvar[item] = True
				self.svar[item] = val
		
		if updateGUI and isIpy() and hasattr(self, 'element'):
			els = self.element.children if self.obj is None else self.element[item].children
			els[0].value = val != False 
			if not isinstance(val, bool): els[1].value = str(val) #Ipy text widget requires a string
		
	#Override because it's a complex type
	def setf(self, item=None):
		def sets(b, s):
			self.set(s if b else False, item, updateGUI=False)
			els = self.element if item is None else self.element[item]
			els.children[1].disabled = not b
		return sets