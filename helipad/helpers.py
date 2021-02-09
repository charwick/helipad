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
		#Remove in Helipad 1.3
		if 'agents_' in index:
			index = index.replace('agents_', 'num_')
			warnings.warn('The use of the \'agents_\' prefix to access the primitive population parameter is deprecated and will be removed in a future version. Use the \'num_\' prefix instead.', None, 3)
		#Remove in Helipad 1.4
		elif index=='updateEvery':
			index = 'refresh'
			warnings.warn('The \'updateEvery\' parameter has been renamed to \'refresh\'. The ability to refer to \'updateEvery\' is deprecated and will be removed in a future version.', None, 3)
		return index

import colorsys, matplotlib.colors as mplcolor
class Color:
	def __init__(self, color):
		if isinstance(color, str): #Can remove the try-except block in Helipad 1.3 or April 2021, whichever is later
			try: self.rgb = mplcolor.hex2color(color) #can take a hex string or a color name
			except ValueError:
				if len(color)==6 or len(color)==3:
					warnings.warn('Initializing a hex color without \'#\' is deprecated and will be removed in a future version. Please add a \'#\' to the beginning of all hex colors.', None, 3)
					self.rgb = mplcolor.hex2color('#'+color)
				else: raise
		else: self.rgb = list(color)
	
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