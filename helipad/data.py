# ==========
# Code for collecting and exporting data from model runs
# Do not run this file; import model.py and run from your file.
# ==========

import pandas, os.path
from numpy import *
from helipad.model import Item

class Data:
	def __init__(self, model):
		self.reporters = {}
		self.model = model
	
	def __getitem__(self, index):
		r = self.columns[index]
		return r.data if index==r.name else r.children[index][1]

	#First arg is the name of the reporter
	#Second arg can be either a function that takes one argument – the model –
	#or a string, either 'model' or the name of a primitive.
	#Subsequent args get passed to the reporter functions below
	def addReporter(self, key, func, **kwargs):
		func, children = func if isinstance(func, tuple) else (func, {})
		
		if not callable(func): raise TypeError('Second argument of addReporter must be callable')
		self.reporters[key] = Reporter(name=key, func=func, children=children, **kwargs)
		return self.reporters[key]
	
	#Removes a reporter, its columns from the data, and the series corresponding to it.
	def removeReporter(self, key):
		if self.model.hasModel:
			raise RuntimeError('removeReporter cannot be called while a model is active.')
		self.model.doHooks('removeReporter', [self, key])
		del self.reporters[key]

	def collect(self, model):
		model.doHooks('dataCollect', [self, model.t])
		for v in self.reporters.values(): v.collect(model)
	
	def reset(self):
		for v in self.reporters.values(): v.clear()
	
	@property
	def all(self):
		data = {}
		for k,r in self.reporters.items():
			data[k] = r.data
			for s,d in r.children.items(): data[s] = d[1]
		return data
	
	@property
	def columns(self):
		cols = {}
		for k,r in self.reporters.items():
			cols[k] = r
			for s in r.children: cols[s] = r
		return cols
	
	@property
	def dataframe(self): return pandas.DataFrame(self.all)
	
	#
	# REPORTERS
	# These functions return reporters; they take some arguments and return a function that takes 1 argument: model.
	#
	
	def modelReporter(self, key):
		def reporter(model): return getattr(model, key)
		return reporter
	
	# NOTE: Batching data collection (looping over agents and then variables, instead of – as now – looping over
	# variables and then agents) did not result in any speed gains; in fact a marginal (0.65%) speed reduction
	def agentReporter(self, key, prim=None, breed=None, good=None, stat='mean', **kwargs):
		if prim is None: prim = next(iter(self.model.primitives))
		# if breed and isinstance(breed, bool): return [self.agentReporter(key+'-'+br, prim, br, good, stat, **kwargs) for br in self.model.primitives[prim].breeds]
		if 'percentiles' in kwargs:
			subplots = {('' if not breed else breed)+key+'-'+str(p)+'-pctile':self.agentReporter(key, prim, breed=breed, good=good, stat='percentile-'+str(p)) for p in kwargs['percentiles']}
		elif 'std' in kwargs:
			subplots = {('' if not breed else breed)+key+'+'+str(kwargs['std'])+'std': self.agentReporter(key, prim, breed=breed, good=good, stat='mstd-p-'+str(kwargs['std'])), key+'-'+str(kwargs['std'])+'std': self.agentReporter(key, prim, breed=breed, good=good, stat='mstd-m-'+str(kwargs['std']))}
		else: subplots = None
		
		def reporter(model):
			u = []
			array = model.allagents.values() if prim=='all' else model.agents[prim]
			
			for agent in array:
				if breed is not None and agent.breed != breed: continue
				v = getattr(agent, key)
				if good is not None: v = v[good] #Narrow to goods. Hackish…
				if v is not None: u.append(v)
			if not u: return 0
			elif stat=='sum':	return sum(u)
			elif stat=='mean':	return mean(u)
			elif stat=='gmean':	return exp(log(u).sum()/len(u))
			elif stat=='std':	return std(u)
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
				if op=='p': return mean(u) + coef * std(u)
				else: return mean(u) - coef * std(u)
			else: raise ValueError('Invalid statistic '+stat)
		return (reporter, subplots) if subplots is not None else reporter
	
	#
	# OTHER FUNCTIONS
	#
	
	#Slices the last n records for the key registered as a reporter
	#Returns a value if n=1, otherwise a list
	def getLast(self, key, n=1):
		if isinstance(key, str):
			if len(self[key])==0: return 0
			data = self[key][-n:]
			return data if n>1 else data[0]
		elif isinstance(key, int):
			return {k: v[-key:] for k,v in self.all.items()}
		else: raise TypeError('First argument of getLast must be either a key name or an int')
	
	def saveCSV(self, filename='data'):
		file = filename + '.csv'
		i=0
		while os.path.isfile(file): #Avoid filename collisions
			i += 1
			file = filename+'-'+str(i)+'.csv'
		self.dataframe.to_csv(file)

class Reporter(Item):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.data = []
		self.children = {k:(fn, []) for k, fn in self.children.items()}
		if not 'smooth' in kwargs: self.smooth = False
		else: self.children[self.name+'-unsmooth'] = (None, [])
	
	def collect(self, model):
		for p, s in self.children.items():
			if callable(s[0]): s[1].append(s[0](model))
		
		if not self.smooth: self.data.append(self.func(model))
		else:
			us = self.children[self.name+'-unsmooth'][1]
			us.append(self.func(model))
			#					  Old data 					   New data point
			self.data.append(self.smooth*self.data[-1] + (1-self.smooth)*us[-1] if model.t>1 else us[-1])
	
	def clear(self):
		self.data.clear()
		for c in self.children.values(): c[1].clear()