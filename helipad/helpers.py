# ==========
# Helper classes and functions used in multiple modules
# None of these are intended to be user-facing
# ==========

import warnings

#Checks for any Ipython environment, including Spyder, for event loop purposes.
def isIpy():
	try:
		__IPYTHON__
		return True
	except NameError: return False

#Check whether Helipad is running in an interactive notebook. However, get_ipython() comes
# back undefined inside callbacks. So cache the value once, the first time it runs.
def isNotebook():
	if not '__helipad_ipy' in globals():
		try:
			globals()['__helipad_ipy'] = 'InteractiveShell' in get_ipython().__class__.__name__
		except NameError: globals()['__helipad_ipy'] = False

	return __helipad_ipy

#Generic extensible item class to store structured data
class Item:
	def __init__(self, **kwargs):
		for k,v in kwargs.items():
			setattr(self, k, v)

class funcStore(dict):
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

#To handle deprecated parameter names
class dictLike(dict):
	def __getitem__(self, index): return super().__getitem__(self.normalize(index))
	def __setitem__(self, index, value): super().__setitem__(self.normalize(index), value)
	def normalize(self, index):
		deprecated = {
			# 'updateEvery': 'refresh'
		}
		if index in deprecated:
			warnings.warn(_('The {0} parameter is deprecated and has been renamed to {1}.').format(index, deprecated[index]), FutureWarning, 3)
			index = deprecated[index]
		return index

import colorsys, matplotlib.colors as mplcolor
class Color:
	def __init__(self, color):
		#Can take a hex string, color name, or [r,g,b] list/tuple.
		self.rgb = mplcolor.hex2color(color) if isinstance(color, str) else list(color)

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
		hls = colorsys.rgb_to_hls(*self.rgb)
		return Color(colorsys.hls_to_rgb(hls[0], (1-1/factor) + hls[1]/factor, hls[2]))

	def darken(self):
		hls = colorsys.rgb_to_hls(*self.rgb)
		return Color(colorsys.hls_to_rgb(hls[0], hls[1]-0.075 if hls[1]>0.075 else 0, hls[2]))

	def blend(self, color2):
		return Color(((self.r+color2.r)/2, (self.g+color2.g)/2, (self.b+color2.b)/2))

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)