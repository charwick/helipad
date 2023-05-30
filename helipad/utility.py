"""
Classes to give agents utility functions, and a base `Utility` class to subclass new utility functions. Built-in utility functions include `CES`, `Leontief`, and `CobbDouglas`.
"""

from abc import ABC, abstractmethod
from helipad.helpers import ï

class Utility(ABC):
	"""A base class defining the methods a utility class must implement. https://helipad.dev/functions/utility/"""

	#Receives an array of goods.
	#Can, but doesn't necessarily have to correspond to the registered goods
	#i.e. you can have an abstract good like real balances
	def __init__(self, goods):
		self.goods = goods
		self.utility = 0

	def consume(self, quantities: dict):
		"""Sets `self.utility` to the value returned from `self.calculate()`. `agent.stocks` can be passed directly to this function. https://helipad.dev/functions/utility/consume/"""
		self.utility = self.calculate(quantities)
		return self.utility

	@abstractmethod
	def calculate(self, quantities: dict):
		"""Calculate the agent's utility on the basis of the array of quantities entered. https://helipad.dev/functions/utility/calculate/"""
		if len(quantities) != len(self.goods): raise KeyError(ï('Quantities argument doesn\'t match initialized list of goods.'))

	@abstractmethod
	def demand(self, budget, prices: dict):
		"""Calculate total demand for the various goods given some income. https://helipad.dev/functions/utility/demand/"""

	@abstractmethod
	def mu(self, quantities: dict):
		"""Calculates the marginal utilities of the goods in question on the basis of the entered quantities. https://helipad.dev/functions/utility/mu/"""
		if len(quantities) != len(self.goods): raise KeyError(ï('Quantities argument doesn\'t match initialized list of goods.'))

	@abstractmethod
	def mrs(self, good1: str, q1, good2: str, q2):
		"""Calculate the marginal rate of substitution between `good1` and `good2` given quantities `q1` and `q2`, respectively. https://helipad.dev/functions/utility/mrs/"""

class CES(Utility):
	"""A constant elasticity of substitution utility function. https://helipad.dev/functions/ces/"""

	#Coefficients should add to 1, but this is not enforced
	#Goods can be a list of goods, or a dict of goods and corresponding coefficients
	def __init__(self, goods, elast):
		if isinstance(goods, dict):
			self.coeffs = goods
			goods = goods.keys()
		else:
			self.coeffs = {g:1 for g in goods}
		super().__init__(goods)
		self.elast = elast

	#Can take agent.goods, if the registered goods correspond
	def calculate(self, quantities):
		super().calculate(quantities)

		#Can't divide by zero in the inner exponent
		#But at σ=0, the utility function becomes a Leontief function in the limit
		#The coefficients don't show up, see https://www.jstor.org/stable/29793581
		if self.elast==0: return min(quantities.values())

		#Can't divide by zero in the outer exponent
		#But at σ=1, the utility function becomes a Cobb-Douglass function
		#See https://yiqianlu.files.wordpress.com/2013/10/ces-functions-and-dixit-stiglitz-formulation.pdf
		elif self.elast==1:
			util = 1
			for g in self.goods:
				util *= quantities[g] ** self.coeffs[g]
			return util

		#Can't raise zero to a negative exponent
		#But as x approaches zero, x^-y approaches infinity
		#So an infinite inner sum means the whole expression becomes zero
		elif (0 in quantities.values()) and self.elast<1: return 0

		#The general utility function
		else:
			util = sum(self.coeffs[g] ** (1/self.elast) * quantities[g] ** ((self.elast-1)/self.elast) for g in self.goods)
			return util ** (self.elast/(self.elast-1))

	def mu(self, quantities):
		super().mu(quantities)

		if self.elast==0:	#Leontief
			mus = {g: 1 if quantities[g] < min(quantities.values()) else 0 for g in self.goods}

		elif self.elast==1:	#Cobb-Douglas
			mus = {}
			for g in self.goods:
				mus[g] = self.coeffs[g] * quantities[g] ** (self.coeffs[g] - 1)
				for g2 in self.goods:
					if g2 != g:
						mus[g] *= quantities[g2] ** self.coeffs[g2]

		else:				#General CES
			coeff = sum(self.coeffs[g] ** (1/self.elast) * quantities[g] ** ((self.elast-1)/self.elast) for g in self.goods)
			coeff = coeff ** (1/(self.elast-1))
			mus = {g: coeff * (self.coeffs[g]/quantities[g]) ** (1/self.elast) for g in self.goods}

		return mus

	#Doesn't depend on any other quantities
	def mrs(self, good1, q1, good2, q2):
		if self.elast==0:
			if q1 < q2: return float('inf')
			elif q1 > q2: return 0
			else: return None #Undefined at the kink in the indifference curve

		#Works for both Cobb-Douglas and the general CES
		else:
			return ((self.coeffs[good1]*q2)/(self.coeffs[good2]*q1)) ** (1/self.elast)

	def demand(self, budget, prices):
		demand = {g:0 for g in self.goods}
		for g in self.goods:
			# Derivation at https://cameronharwick.com/blog/how-to-derive-a-demand-function-from-a-ces-utility-function/
			for h, price in prices.items():
				demand[g] += self.coeffs[h]/self.coeffs[g] * price ** (1-self.elast)
			demand[g] = budget * prices[g] ** (-self.elast) / demand[g]

		return demand

class CobbDouglas(CES):
	"""A Cobb-Douglas utility function. `Goods` can be a list of goods, or a dict of goods and corresponding exponents. https://helipad.dev/functions/cobbdouglas/"""
	def __init__(self, goods):
		if isinstance(goods, list):
			goods = {g:1/len(goods) for g in goods}

		super().__init__(goods, 1)

	@property
	def exponents(self): return self.coeffs

class Leontief(CES):
	"""A Leontief utility function, where utility is equal to the minimum quantity held of any relevant good. https://helipad.dev/functions/leontief/"""
	def __init__(self, goods):
		super().__init__(goods, 0)