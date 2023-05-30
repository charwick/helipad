"""
Classes for collecting and exporting data from model runs. This module should not be imported directly; interface with the `model.data` container object instead. See https://helipad.dev/functions/data/
"""

import pandas, os.path
import numpy as np
from helipad.helpers import Item, ï

#Don't try to subclass Pandas.dataframe; substantially slower and doesn't scale
class Data:
	"""Interface for collecting, storing, and accessing data generated during model runs. The object is subscriptable: `data[key]` will return the column of the data labelled `key`. Stored in `model.data`. https://helipad.dev/functions/data/"""
	def __init__(self, model):
		self.reporters = {}
		self.model = model

	def __getitem__(self, index):
		r = self.columns[index]
		return r.data if index==r.name else r.children[index][1]

	def __contains__(self, index): return index in self.columns
	def __repr__(self): return f'<{self.__class__.__name__}: {len(self.reporters)} reporters>'

	def addReporter(self, key: str, func, **kwargs):
		"""Register a column in the data to be collected each period. `func` can either be a function that takes the model object as its only argument and returns a value, or a string - either `model` or the name of a primitive. Kwargs are passed to the reporter class. https://helipad.dev/functions/data/addreporter/"""
		func, children = func if isinstance(func, tuple) else (func, {})

		if not callable(func): raise TypeError(ï('Second argument of addReporter must be callable.'))
		self.reporters[key] = Reporter(name=key, func=func, children=children, **kwargs)
		return self.reporters[key]

	def removeReporter(self, key: str):
		"""Remove a column and its subsidiaries (e.g. percentiles) from the data collection, stop its reporter, and remove any associated series. https://helipad.dev/functions/data/removereporter/"""
		if self.model.hasModel:
			raise RuntimeError(ï('removeReporter cannot be called while a model is active.'))
		self.model.doHooks('removeReporter', [self, key])
		del self.reporters[key]

	def collect(self, model):
		"""Iterate over all the registered reporters and collect model data each period. This function is called from `model.step()` and should not be called from user code. https://helipad.dev/functions/data/collect/"""
		model.doHooks('dataCollect', [self, model.t])
		for v in self.reporters.values(): v.collect(model)

	def reset(self):
		"""Clear all model data. Generally used to clean up between model runs. https://helipad.dev/functions/data/reset/"""
		for v in self.reporters.values(): v.clear()

	@property
	def all(self) -> dict:
		"""A dict of all model data, with keys corresponding to registered reporters. https://helipad.dev/functions/data/#all"""
		data = {}
		for k,r in self.reporters.items():
			data[k] = r.data
			for s,d in r.children.items(): data[s] = d[1]
		return data

	@property
	def columns(self) -> dict:
		"""A `dict` of data columns and the associated Reporter objects. This property does not correspond to `Data.reporters.keys()`, because multiple columns may be associated with the same reporter (e.g. with percentile bars, smoothing, or ± standard deviations). https://helipad.dev/functions/data/#columns"""
		cols = {}
		for k,r in self.reporters.items():
			cols[k] = r
			for s in r.children: cols[s] = r
		return cols

	@property
	def dataframe(self):
		"""A `Pandas` dataframe with the model run data. https://helipad.dev/functions/data/#dataframe"""
		return pandas.DataFrame(self.all)

	#
	# REPORTERS
	# These functions return reporters; they take some arguments and return a function that takes 1 argument: model.
	#

	def modelReporter(self, key):
		"""Generate a reporter function that takes the `model` object and returns the named attribute of the model. https://helipad.dev/functions/data/modelreporter/"""
		def reporter(model): return getattr(model, key)
		return reporter

	# NOTE: Batching data collection (looping over agents and then variables, instead of – as now – looping over
	# variables and then agents) did not result in any speed gains; in fact a marginal (0.65%) speed reduction
	def agentReporter(self, key: str, prim=None, breed=None, good=None, stat: str='mean', **kwargs):
		"""Generate a reporter function that takes the `model` object and returns a summary statistic (`'mean'`, `'sum'`, `'gmean'` (for geometric mean), `'std'` (for standard deviation), or `'percentile-nn'`, where `nn` is a number from 0-100.) over all the values of an agent property. https://helipad.dev/functions/data/agentreporter/"""
		if prim is None: prim = next(iter(self.model.agents))
		# if breed and isinstance(breed, bool): return [self.agentReporter(key+'-'+br, prim, br, good, stat, **kwargs) for br in self.model.agents[prim].breeds]
		if 'percentiles' in kwargs:
			subplots = {('' if not breed else breed)+key+'-'+str(p)+'-pctile':self.agentReporter(key, prim, breed=breed, good=good, stat='percentile-'+str(p)) for p in kwargs['percentiles']}
		elif 'std' in kwargs:
			subplots = {('' if not breed else breed)+key+'+'+str(kwargs['std'])+'std': self.agentReporter(key, prim, breed=breed, good=good, stat='mstd-p-'+str(kwargs['std'])), key+'-'+str(kwargs['std'])+'std': self.agentReporter(key, prim, breed=breed, good=good, stat='mstd-m-'+str(kwargs['std']))}
		else: subplots = None

		def reporter(model):
			#Construct list of values
			array = [getattr(a, key) for a in (model.agents.all if prim=='all' else model.agents[prim]) if breed is None or breed==a.breed]
			if good is not None: array = [v[good] for v in array]
			u = [v for v in array if v is not None]

			if not u: return 0
			elif stat=='sum':	return sum(u)
			elif stat=='mean':	return np.mean(u)
			elif stat=='gmean':	return np.exp(np.log(u).sum()/len(u))
			elif stat=='std':	return np.std(u)
			elif stat=='max':	return max(u)
			elif stat=='min':	return min(u)
			elif 'percentile-' in stat:
				pctile = int(stat.split('-')[1])
				if pctile==100: return max(u)
				elif pctile==0: return min(u)
				else:
					u.sort()
					idx = round(len(u)*pctile/100)
					return u[idx] if len(u)>=idx+1 else u[0]
			elif 'mstd-' in stat: #Don't use directly; use the std kwarg
				s, op, coef = stat.split('-')
				coef = float(coef)
				if op=='p': return np.mean(u) + coef * np.std(u)
				else: return np.mean(u) - coef * np.std(u)
			else: raise ValueError(ï('Invalid statistic {}.').format(stat))
		return (reporter, subplots) if subplots is not None else reporter

	#
	# OTHER FUNCTIONS
	#

	#Slices the last n records for the key registered as a reporter
	#Returns a value if n=1, otherwise a list
	def getLast(self, key: str, n: int=1):
		"""Return the latest recorded value or values from the model's data. https://helipad.dev/functions/data/getlast/"""
		if isinstance(key, str):
			if len(self[key])==0: return 0
			data = self[key][-n:]
			return data if n>1 else data[0]
		elif isinstance(key, int):
			return {k: v[-key:] for k,v in self.all.items()}
		else: raise TypeError(ï('First argument of Data.getLast() must be either a key name or an int.'))

	def saveCSV(self, filename: str='data'):
		"""Outputs the model's data to a CSV file in the same directory as the running program. https://helipad.dev/functions/data/savecsv/"""
		file = filename + '.csv'
		i=0
		while os.path.isfile(file): #Avoid filename collisions
			i += 1
			file = filename+'-'+str(i)+'.csv'

		df = self.dataframe
		hook = self.model.doHooks('saveCSV', [df, self.model]) #can't do `or None` since "The truth value of a DataFrame is ambiguous"
		if hook is not None: df = hook
		df.to_csv(file)

class Reporter(Item):
	"""An interface defining a single column of data to be collected during a model run. https://helipad.dev/functions/reporter/"""
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.data = []
		self.children = {k:(fn, []) for k, fn in self.children.items()}
		if 'smooth' not in kwargs: self.smooth = False
		else: self.children[self.name+'-unsmooth'] = (None, [])

	def collect(self, model):
		"""Run the reporter function and its children, and append the results to the data. https://helipad.dev/functions/reporter/collect/"""
		for s in self.children.values():
			if callable(s[0]): s[1].append(s[0](model))

		if not self.smooth: self.data.append(self.func(model))
		else:
			us = self.children[self.name+'-unsmooth'][1]
			us.append(self.func(model))
			#					  Old data 					   New data point
			self.data.append(self.smooth*self.data[-1] + (1-self.smooth)*us[-1] if model.t>1 else us[-1])

	def clear(self):
		"""Empty the reporter's collected data. https://helipad.dev/functions/reporter/clear/"""
		self.data.clear()
		for c in self.children.values(): c[1].clear()