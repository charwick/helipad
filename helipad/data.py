# ==========
# Code for collecting and exporting data from model runs
# Do not run this file; import model.py and run from your file.
# ==========

import pandas, os.path
from numpy import *

class Data():
	def __init__(self, model):
		self.all = {}			#Data
		self.reporters = {}
		self.model = model
	
	def __getitem__(self, index): return self.all[index]
	def __setitem__(self, index, value): self.all[index] = value

	#First arg is the name of the reporter
	#Second arg can be either a function that takes one argument – the model –
	#or a string, either 'model' or the name of a primitive.
	#Subsequent args get passed to the reporter functions below
	def addReporter(self, key, func, **kwargs):
		
		#Create column space for percentile marks
		if isinstance(func, tuple):
			mainfunc, subplots = func
			for p, s in subplots.items():
				self[key+'-'+str(p)+'-pctile'] = []
		else: mainfunc = func
		
		#If smoothing, shunt original reporter to -unsmooth and create a new series under the original name
		if 'smooth' in kwargs:
			def smooth(weight, k):
				def movingAvg(data, t):
					#					  Old data 					   New data point
					data[k].append(weight*data[k][-1] + (1-weight)*data[k+'-unsmooth'][-1] if t>1 else data[k+'-unsmooth'][-1])
				return movingAvg
				
			self.model.addHook('dataCollect', smooth(kwargs['smooth'], key))
			self[key] = []
			key += '-unsmooth'
		
		if not callable(mainfunc): raise TypeError('Second argument of addReporter must be callable')
		self.reporters[key] = func
		self[key] = []

	def collect(self, model):
		for var, reporter in self.reporters.items():
			if isinstance(reporter, tuple):
				reporter, subplots = reporter
				for p, s in subplots.items():
					self[var+'-'+str(p)+'-pctile'].append(s(model))
			self[var].append(reporter(model))
		model.doHooks('dataCollect', [self, model.t])
	
	def reset(self):
		self.all = {k: [] for k in self.all.keys()}
	
	@property
	def dataframe(self):
		return pandas.DataFrame(self.all)
	
	#
	# REPORTERS
	# These functions return reporters; they take some arguments and return a function that takes 1 argument: model.
	#
	
	def modelReporter(self, key):
		def reporter(model): return getattr(model, key)
		return reporter
	
	# NOTE: Batching data collection (looping over agents and then variables, instead of – as now – looping over
	# variables and then agents) did not result in any speed gains; in fact a marginal (0.65%) speed reduction
	def agentReporter(self, key, prim='agent', breed=None, good=None, stat='mean', **kwargs):
		if 'percentiles' in kwargs:
			subplots = {}
			for p in kwargs['percentiles']:
				subplots[p] = self.agentReporter(key, prim, breed=breed, good=good, stat='percentile-'+str(p))
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
			elif 'percentile-' in stat:
				pctile = int(stat.split('-')[1])
				if pctile==100: return max(u)
				elif pctile==0: return min(u)
				else:
					u.sort()
					idx = round(len(u)*pctile/100)
					return u[idx] if len(u)>=idx+1 else u[0]
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