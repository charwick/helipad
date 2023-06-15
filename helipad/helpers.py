"""
Helper classes and functions used internally in Helipad. This module should not be imported directly.
"""

import warnings
from sys import __stdout__
from io import BufferedWriter

#Using _ is a disaster. Can't install to global scope because it conflicts with readline;
#Can't name it _ here because `import *` skips it
def ï(text) -> str:
	"""Internationalization. Named so as to avoid a conflict with `_` in the REPL console."""
	return helipad_gettext(text)

def isIpy() -> bool:
	"""Check for any Ipython environment, including Spyder, for event loop purposes."""
	try:
		__IPYTHON__
		return True
	except NameError: return False

def isNotebook() -> bool:
	"""Check whether Helipad is running in an interactive notebook."""
	#get_ipython() comes back undefined inside callbacks. So cache the value once, the first time it runs.
	#Can try @functools.cache when Python 3.9 is required
	if not '__helipad_ipy' in globals():
		try:
			globals()['__helipad_ipy'] = 'InteractiveShell' in get_ipython().__class__.__name__
		except NameError: globals()['__helipad_ipy'] = False

	return __helipad_ipy

def isBuffered() -> bool:
	"""Check whether the current Python script is running in a buffered or unbuffered console."""
	return isinstance(__stdout__.buffer, BufferedWriter)

class Item:
	"""A generic extensible item class to store structured data. Kwargs are stored as object properties."""
	def __init__(self, **kwargs):
		for k,v in kwargs.items():
			setattr(self, k, v)

class funcStore(dict):
	"""A generic dict-like container class. https://helipad.dev/functions/funcstore/"""
	multi = False

	def add(self, name, function):
		if self.multi:
			if name not in self: self[name] = [function]
			else: self[name].append(function)
		else: self[name] = function
		return function

	def remove(self, name, fname=None, removeall=False):
		if isinstance(name, (list, tuple)): return [self.remove(n) for n in name]
		if name not in self: return False
		if self.multi and fname:
			if isinstance(fname, (list, tuple)): return [self.remove(name, f, removeall) for f in fname]
			did = False
			for h in self[name]:
				if h.__name__ == fname:
					self[name].remove(h)
					if not removeall: return True
					else: did = True
			return did
		else:
			del self[name]
			return True

import colorsys, matplotlib.colors as mplcolor
class Color:
	"""Defines a color and provides functions to manipulate it. https://helipad.dev/functions/color/"""
	def __init__(self, color):
		#Can take a hex string, color name, or [r,g,b] list/tuple.
		self.rgb = mplcolor.hex2color(color) if isinstance(color, str) else list(color)

	def __repr__(self): return f'<Color: ({round(self.r*100)},{round(self.g*100)},{round(self.b*100)})>'

	@property
	def hex(self): return mplcolor.to_hex(self.rgb)
	@property
	def hsv(self): return list(mplcolor.rgb_to_hsv(self.rgb))
	@property
	def r(self): return self.rgb[0]
	@property
	def g(self): return self.rgb[1]
	@property
	def b(self): return self.rgb[2]
	@property
	def h(self): return self.hsv[0]
	@property
	def s(self): return self.hsv[1]
	@property
	def v(self): return self.hsv[2]

	def lighten(self, factor=3):
		"""Creates a new color, lighter than the existing color by `factor`."""
		hls = colorsys.rgb_to_hls(*self.rgb)
		return Color(colorsys.hls_to_rgb(hls[0], (1-1/factor) + hls[1]/factor, hls[2]))

	def darken(self):
		"""Create a new color, slightly darker than the original."""
		hls = colorsys.rgb_to_hls(*self.rgb)
		return Color(colorsys.hls_to_rgb(hls[0], hls[1]-0.075 if hls[1]>0.075 else 0, hls[2]))

	def blend(self, color2):
		"""Create a new color halfway between the existing color and another. https://helipad.dev/functions/color/blend/"""
		return Color(((self.r+color2.r)/2, (self.g+color2.g)/2, (self.b+color2.b)/2))

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)