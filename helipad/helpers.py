# ==========
# Helper classes and functions used in multiple modules
# None of these are intended to be user-facing
# ==========

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