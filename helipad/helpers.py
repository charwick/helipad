# ==========
# Helper classes and functions used in multiple modules
# None of these are intended to be user-facing
# ==========

import warnings

def isIpy():
	try:
		__IPYTHON__
		return True
	except NameError: return False

#Generic extensible item class to store structured data
class Item:
	def __init__(self, **kwargs):
		for k,v in kwargs.items():
			setattr(self, k, v)

#To handle deprecated parameter names
class dictLike(dict):
	def __getitem__(self, index): return super().__getitem__(self.normalize(index))
	def __setitem__(self, index, value): super().__setitem__(self.normalize(index), value)
	def normalize(self, index):
		#Remove in Helipad 1.4
		if index=='updateEvery':
			index = 'refresh'
			warnings.warn('The \'updateEvery\' parameter has been renamed to \'refresh\'. The ability to refer to \'updateEvery\' is deprecated and will be removed in a future version.', None, 3)
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
	
	def blend(self, color2):
		return Color(((self.r+color2.r)/2, (self.g+color2.g)/2, (self.b+color2.b)/2))