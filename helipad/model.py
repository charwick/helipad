# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========

import sys, warnings, pandas
from random import shuffle, choice
from numpy import random
from helipad.graph import *
from helipad.helpers import *
from helipad.param import *
import matplotlib, asyncio
# import time	#For performance testing

if not isIpy():
	from tkinter import *
	matplotlib.use('TkAgg')
else: matplotlib.use('nbagg')

from helipad.data import Data
import helipad.agent as agent

class Helipad:
	runInit = True #for multiple inheritance
	
	def __init__(self):
		self.data = Data(self)
		self.shocks = Shocks(self)
		self.running = False
		
		self.name = ''
		self.agents = {}
		self.primitives = {}
		self.params = dictLike()#Global parameters
		self.goods = {}			#List of goods
		self.goodParams = {}	#Per-good parameters
		self.hooks = {}			#External functions to run
		self.stages = 1
		self.order = 'linear'
		self.hasModel = False	#Have we initialized?
		self.moneyGood = None
		self.allEdges = {}
		
		#Default parameters
		self.addPrimitive('agent', agent.Agent, dflt=50, low=1, high=100)
		
		#Decorators
		def repdec(name, fn, kwargs): self.data.addReporter(name, fn, **kwargs)
		def hookdec(name, fn, kwargs): self.addHook(name, fn, **kwargs)
		def buttondec(name, fn, kwargs): self.addButton(name, fn, **kwargs)
		self.reporter = self.genDecorator(repdec)
		self.hook = self.genDecorator(hookdec)
		self.button = self.genDecorator(buttondec)
		
		#A few things that only make sense to do if it's the topmost model
		if not hasattr(self, 'breed'):
			if not isIpy(): self.root = Tk() #Got to initialize Tkinter first in order for StringVar() and such to work
			
			#Privileged parameters
			#Toggle the progress bar between determinate and indeterminate when stopafter gets changed
			def switchPbar(model, name, val):
				if not model.hasModel or not getattr(model, 'cpanel', False) or not getattr(model.cpanel, 'progress', False): return
				if not val: self.cpanel.progress.determinate(False)
				else:
					self.cpanel.progress.determinate(True)
					self.cpanel.progress.update(model.t/val)
			self.addParameter('stopafter', 'Stop on period', 'checkentry', False, runtime=True, config=True, entryType='int', callback=switchPbar)
			self.addParameter('csv', 'CSV?', 'checkentry', False, runtime=True, config=True)
			self.addParameter('updateEvery', 'Refresh Every __ Periods', 'slider', 20, opts=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], runtime=True, config=True)
			self.addParameter('plots', 'Plots', 'checkgrid', [], opts={}, runtime=False, config=True)
			
			#Plot categories
			self.plots = {}
			plotList = {
				'demand': 'Demand',
				'shortage': 'Shortages',
				'money': 'Money',
				'utility': 'Utility'
			}
			for name, label in plotList.items(): self.addPlot(name, label, selected=False)
		
			#Check for updates
			from helipad.__init__ import __version__
			import xmlrpc.client, ssl
		
			#Is v1 bigger than v2?
			#There's a `packaging` function to do this, but let's not bloat our dependencies.
			def vcompare(v1, v2):
				(v1, v2) = (v1.split('.'), (v2.split('.')))
			
				#Pad major releases with zeroes to make comparable
				maxl = max([len(v1), len(v2)])
				for v in [v1,v2]:
					if len(v)<maxl: v += [0 for i in range(maxl-len(v))]
			
				for k,i in enumerate(v1):
					if i > v2[k]: return True
					elif i < v2[k]: return False
				return False
		
			try:
				pypi = xmlrpc.client.ServerProxy('https://pypi.org/pypi', context=ssl._create_unverified_context())
				available = pypi.package_releases('helipad')
				if vcompare(available[0], __version__):
					print('A Helipad update is available! Use `pip install -U helipad` to upgrade to version',available[0])
			except: pass #Fail silently if we're not online
	
	def addPrimitive(self, name, class_, plural=None, dflt=50, low=1, high=100, step=1, hidden=False, priority=100, order=None):
		if name=='all': raise ValueError(name+' is a reserved name. Please choose another.')
		if not plural: plural = name+'s'
		class_.primitive = name
		self.primitives[name] = Item(
			class_=class_,
			plural=plural,
			priority=priority,
			order=order,
			breeds={},
			breedParams={}
		)
		def popget(name, model):
			prim = name.split('_')[1]
			if not model.hasModel: return None
			else: return len(model.agents[prim])
			
		self.addParameter('num_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step} if not hidden else None, setter=self.nUpdater, getter=popget)
		self.agents[name] = []
	
	def removePrimitive(self, name):
		del self.primitives[name]
		del self.agents[name]
		del self.params['num_'+name]
		
	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, selected=True, logscale=False, stack=False):
		if getattr(self, 'cpanel', False):
			if isIpy(): self.cpanel.invalidate()
			else: raise RuntimeError('Cannot add plots after control panel is drawn')
		plot = Plot(model=self, name=name, label=label, series=[], logscale=logscale, stack=stack, selected=selected)
		if position is None or position > len(self.plots):
			self.params['plots'].opts[name] = label
			self.plots[name] = plot
		else:		#Reconstruct the dicts because there's no insert method…
			newopts, newplots, i = ({}, {}, 1)
			for k,v in self.params['plots'].opts.items():
				if position==i:
					newopts[name] = label
					newplots[name] = plot
				newopts[k] = v
				newplots[k] = self.plots[k]
				i+=1
			self.params['plots'].opts = newopts
			self.plots = newplots
		
		self.params['plots'].vars[name] = selected
		if selected: self.params['plots'].default.append(name)
		if getattr(self, 'cpanel', False) and not self.cpanel.valid: self.cpanel.__init__(self, redraw=True) #Redraw if necessary
		
		return plot
	
	def removePlot(self, name, reassign=None):
		if getattr(self, 'cpanel', False): raise RuntimeError('Cannot remove plots after control panel is drawn')
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return
		
		if not name in self.plots:
			warnings.warn('No plot \''+name+'\' to remove', None, 2)
			return
				
		if reassign is not None: self.plots[reassign].series += self.plots[name].series
		del self.plots[name]
		del self.params['plots'].opts[name]
		del self.params['plots'].vars[name]
		if name in self.params['plots'].default: self.params['plots'].default.remove(name)
	
	#First arg is the plot it's a part of
	#Second arg is a reporter name registered in DataCollector, or a lambda function
	#Third arg is the series name. Use '' to not show in the legend.
	#Fourth arg is the plot's hex color, or a Color object
	def addSeries(self, plot, reporter, label, color, style='-'):
		if hasattr(self, 'breed'): return #Doesn't matter if it's not the top-level model
		if not isinstance(color, Color): color = Color(color)
		if not plot in self.plots:
			raise KeyError('Plot \''+plot+'\' does not exist. Be sure to register plots before adding series.')
		#Check against columns and not reporters so percentiles work
		if not callable(reporter) and not reporter in self.data.all:
			raise KeyError('Reporter \''+reporter+'\' does not exist. Be sure to register reporters before adding series.')
		
		#Add subsidiary series (e.g. percentile bars)
		subseries = []
		if reporter in self.data.reporters and isinstance(self.data.reporters[reporter].func, tuple):
			for p, f in self.data.reporters[reporter].func[1].items():
				subkey = reporter+'-'+str(p)+'-pctile'
				subseries.append(self.addSeries(plot, subkey, '', color.lighten(), style='--'))

		#Since many series are added at setup time, we have to de-dupe
		for s in self.plots[plot].series:
			if s.reporter == reporter:
				self.plots[plot].series.remove(s)
		
		series = Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=plot)
		self.plots[plot].series.append(series)
		if reporter in self.data.reporters: self.data.reporters[reporter].series.append(series)
		return series
	
	def addButton(self, text, func, desc=None):
		self.shocks.register(text, None, func, 'button', True, desc)
	
	#Get ready to actually run the model
	def setup(self):
		self.doHooks('modelPreSetup', [self])
		self.t = 0
		
		#Blank breeds for any primitives not otherwise specified
		for k,p in self.primitives.items():
			if len(p.breeds)==0: self.addBreed('', '#000000', prim=k)
		
		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point
		
		self.data.reset()
		defPrim = 'agent' if 'agent' in self.primitives else next(iter(self.primitives))
		
		def pReporter(param, item=None):
			def reporter(model): return param.get(item)
			return reporter
		
		#Add reporters for all parameters
		for item, i in self.goods.items():				#Cycle through goods
			for n,p in self.goodParams.items():			#Cycle through parameters
				if p.type == 'hidden': continue			#Skip hidden parameters
				self.data.addReporter(n+'-'+item, pReporter(p, item))
		for prim, pdata in self.primitives.items():		#Cycle through primitives
			for breed, i in pdata.breeds.items():		#Cycle through breeds
				for n,p in pdata.breedParams.items():	#Cycle through parameters
					if p.type == 'hidden': continue		#Skip hidden parameters
					self.data.addReporter(prim+'-'+n+'-'+item, pReporter(p, breed))
		for n,p in self.params.items():					#Cycle through parameters
			if p.type == 'hidden' or getattr(p, 'config', False): continue	#Skip hidden and config parameters
			self.data.addReporter(n, pReporter(p))

		if (self.moneyGood is not None):
			self.data.addReporter('M0', self.data.agentReporter('stocks', 'all', good=self.moneyGood, stat='sum'))
			self.addSeries('money', 'M0', 'Monetary Base', self.goods[self.moneyGood].color)
		
		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils', defPrim))
		
		#Per-breed and per-good series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in next(iter(self.primitives.values())).breeds.items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', defPrim, breed=breed))
			self.addSeries('utility', 'utility-'+breed, breed.title()+' Utility', b.color)
	
		if len(self.goods) >= 2:
			for good, g in self.nonMoneyGoods.items():
				self.data.addReporter('demand-'+good, self.data.agentReporter('currentDemand', 'all', good=good, stat='sum'))
				self.addSeries('demand', 'demand-'+good, good.title()+' Demand', g.color)
				self.data.addReporter('shortage-'+good, self.data.agentReporter('currentShortage', 'all', good=good, stat='sum'))
				self.addSeries('shortage', 'shortage-'+good, good.title()+' Shortage', g.color)
		
		#Initialize agents
		self.primitives = {k:v for k, v in sorted(self.primitives.items(), key=lambda d: d[1].priority)}	#Sort by priority
		pops = {prim: self.param('num_'+prim) for prim in self.primitives.keys()}
		self.agents = {k: [] for k in self.primitives.keys()}												#Clear any surviving agents from last run
		for prim in self.primitives: self.nUpdater(pops[prim], prim, self, force=True)						#Force is so we can call nupdater before instantiating hasModel
		self.hasModel = True
		
		self.doHooks('modelPostSetup', [self])
			
	#Registers an adjustable parameter exposed in the control panel.	
	def addParameter(self, name, title, type, dflt, opts={}, runtime=True, callback=None, paramType=None, desc=None, prim=None, getter=None, setter=None, **args):
		if paramType is None: params=self.params
		elif paramType=='breed': params=self.primitives[prim].breedParams
		elif paramType=='good': params=self.goodParams
		else: raise ValueError('Invalid object \''+paramType+'\'')
		
		if name in params: warnings.warn('Parameter \''+name+'\' already defined. Overriding…', None, 2)
		
		if callable(getter):
			args['getter'] = lambda item=None: getter(*([name, self] if paramType is None else [name, self, item]))
		
		if callable(setter):
			args['setter'] = lambda val, item=None: setter(*([val, name, self] if paramType is None else [val, name, self, item]))
		
		args.update({
			'name': name,
			'title': title,
			'default': dflt,
			'opts': opts,
			'runtime': runtime,
			'callback': callback,
			'desc': desc,
			'obj': paramType
		})
		if paramType is not None:
			args['keys'] = self.primitives[prim].breeds if paramType=='breed' else self.goods
		
		if type.title()+'Param' in globals(): pclass = globals()[type.title()+'Param']
		else:
			pclass = Param
			args['type'] = type
		params[name] = pclass(**args)
		if getattr(self, 'cpanel', False) and isIpy(): self.cpanel.__init__(self, redraw=True) #Redraw if necessary
	
	def addBreedParam(self, name, title, type, dflt, opts={}, prim=None, runtime=True, callback=None, desc=None, getter=None, setter=None):
		if prim is None:
			if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc, prim=prim, getter=getter, setter=setter)
	
	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None, getter=None, setter=None):
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc, getter=getter, setter=setter)
	
	#Get or set a parameter, depending on whether there are two or three arguments
	def param(self, param, val=None):
		item = param[2] if isinstance(param, tuple) and len(param)>2 else None
		param = self.parseParamId(param)
		
		if val is not None: param.set(val, item)
		else: return param.get(item)
	
	@property
	def allParams(self):
		yield from self.params.values()
		yield from self.goodParams.values()
		for p in self.primitives.values(): yield from p.breedParams.values()
	
	#Parses a parameter identifier tuple and returns a Param object
	#For internal use only
	def parseParamId(self, p):
		if not isinstance(p, tuple): p = (p,)
		if len(p)==1:		return self.params[p[0]]
		elif p[1]=='good':	return self.goodParams[p[0]]
		elif p[1]=='breed':
			if len(p)<4 or p[3] is None:
				if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
				else: raise KeyError('Breed parameter must specify which primitive it belongs to')
			else: prim = p[3]
			return self.primitives[prim].breedParams[p[0]]
	
	#For adding breeds and goods. Should not be called directly
	def addItem(self, obj, name, color, prim=None, **kwargs):
		if obj=='good':
			itemDict = self.goods
			paramDict = self.goodParams
		elif obj=='breed': 
			itemDict = self.primitives[prim].breeds
			paramDict = self.primitives[prim].breedParams
		else: raise ValueError('addItem obj parameter can only take either \'good\' or \'breed\'');
		
		if name in itemDict:
			warnings.warn(obj+' \''+name+'\' already defined. Overriding…', None, 2)
		
		cobj = color if isinstance(color, Color) else Color(color)
		cobj2 = cobj.lighten()
		itemDict[name] = Item(color=cobj, color2=cobj2, **kwargs)
		
		#Make sure the parameter lists keep up with our items
		for k,p in paramDict.items(): p.addKey(name)
		
		return itemDict[name]
	
	def addBreed(self, name, color, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
			else: raise KeyError('Breed must specify which primitive it belongs to')
		return self.addItem('breed', name, color, prim=prim)
		
	def addGood(self, name, color, endowment=None, money=False):
		if money:
			if self.moneyGood is not None: print('Money good already specified as',self.moneyGood,'. Overriding…')
			self.moneyGood = name
		return self.addItem('good', name, color, endowment=endowment, money=money)
	
	@property
	def nonMoneyGoods(self):
		return {k:v for k,v in self.goods.items() if not v.money}
			
	def addHook(self, place, func, prioritize=False):
		if not place in self.hooks: self.hooks[place] = []
		if prioritize: self.hooks[place].insert(0, func)
		else: self.hooks[place].append(func)
	
	#Returns the value of the last function in the list
	def doHooks(self, place, args):
		#Take a list of hooks; go until we get a response
		if isinstance(place, list):
			for f in place:
				r = self.doHooks(f, args)
				if r is not None: return r
			return None
		
		if not place in self.hooks: return None
		for f in self.hooks[place]: r = f(*args)
		return r
				
	def step(self, stage=1):
		self.t += 1
		if hasattr(self, 'dontStepAgents') and self.dontStepAgents: return self.t
		self.doHooks('modelPreStep', [self])
		
		#Reset per-period variables
		#Have to do this all at once at the beginning of the period, not when each agent steps
		for p in self.agents.values():
			for a in p:
				a.currentDemand = {g:0 for g in self.goods.keys()}
				a.currentShortage = {g:0 for g in self.goods.keys()}
		
		self.shocks.step()
		
		def sortFunc(model, stage, func):
			def sf(agent): return func(agent, model, stage)
			return sf
			
		for self.stage in range(1, self.stages+1):
			self.doHooks('modelStep', [self, self.stage])
			
			#Sort agents and step them
			for prim, lst in self.agents.items():
				order = self.primitives[prim].order or self.order
				if isinstance(order, list): order = order[self.stage-1]
				
				if order == 'random': shuffle(lst)
				
				#Can't do our regular doHooks() here since we want to pass the function to .sort()
				#From the user's perspective though, this doesn't matter
				#Do the more specific sorts last
				ordhooks = (self.hooks['order'] if 'order' in self.hooks else []) + (self.hooks[prim+'Order'] if prim+'Order' in self.hooks else [])
				for o in ordhooks: lst.sort(key=sortFunc(self, self.stage, o))
				
				#Matching model
				if 'match' in order:
					matchN = order.split('-')
					matchN = int(matchN[1]) if len(matchN) > 1 else 2
					pool = self.agents[prim].copy()
					while len(pool) > len(self.agents[prim]) % matchN:
						agents = []
						for a in range(matchN):
							agent = choice(pool)
							pool.remove(agent)
							agents.append(agent)
							
							#Allow selection of matches, but only on the first agent
							if a==0:
								others = self.doHooks('matchSelect', [agent, pool, self, self.stage])
								if others is not None:
									if (isinstance(others, agent.baseAgent) and matchN==2): others = [others]
									if (isinstance(others, list) and len(others)==matchN-1):
										for other in others: pool.remove(other)
										agents += others
										break
									else: raise ValueError('matchSelect did not return the correct number of agents.')
									
						accept = self.doHooks('matchAccept', agents)
						if accept is not None and not accept:
							pool = agents + pool #Prepend agents to decrease the likelihood of a repeat matching
							continue
						for a in agents: agent.step(self.stage)
						self.doHooks([prim+'Match', 'match'], [agents, prim, self, self.stage])
					
					#Step any remainder agents
					for agent in pool: agent.step(self.stage)
				
				#Activation model
				else:
					for a in self.agents[prim]:
						a.step(self.stage)
		
		self.data.collect(self)
		self.doHooks('modelPostStep', [self])
		return self.t
	
	#This is split out as an async function to allow user input while running the loop in Jupyter
	async def run(self):
		# self.begin = time.time()
		while self.running:
			t = self.step()
			st = self.param('stopafter')
			
			if t%self.param('updateEvery')==0:
				if getattr(self, 'cpanel', False) and st and not callable(st): self.cpanel.progress.update(t/st)
				
				#Update graph
				if getattr(self, 'graph', None) is not None:
					await asyncio.sleep(0.001) #Listen for keyboard input
					data = self.data.getLast(t - self.graph.lastUpdate)
	
					if (self.graph.resolution > 1):
						data = {k: keepEvery(v, self.graph.resolution) for k,v in data.items()}
					self.graph.update(data)
					self.graph.lastUpdate = t
					if self.graph.resolution > self.param('updateEvery'): self.param('updateEvery', self.graph.resolution)
				
					self.doHooks('graphUpdate', [self, self.graph])
				
				elif getattr(self, 'cpanel', None):
					if isIpy(): await asyncio.sleep(0.001) #Listen for keyboard input
					else: self.root.update() #Make sure we don't hang the interface if plotless
			
				# # Performance indicator
				# newtime = time.time()
				# print('Period', t, 'at', self.param('updateEvery')/(newtime-self.begin), 'periods/second')
				# self.begin = newtime
	
			if st:
				stop = st(self) if callable(st) else t>=st
				if stop: self.terminate()
	
	#The *args allows it to be used as an Ipywidgets callback
	def start(self, *args):
		if getattr(self, 'cpanel', None):
			self.cpanel.progress.start()
			self.cpanel.runButton.run()
		self.doHooks('modelStart', [self, self.hasModel])
		if not self.hasModel: self.setup()
		self.running = True
		
		#Suppress the 'coroutine never awaited' warning, because the interpreter doesn't like the fact
		#that the statement in the try block doesn't get executed…?
		with warnings.catch_warnings():
			warnings.simplefilter("ignore")
			try: asyncio.run(self.run())	#If Tkinter, it needs an event loop
			except:							#If Jupyter, it already has an event loop
				asyncio.ensure_future(self.run())
	
	def stop(self, *args):
		self.running = False
		if getattr(self, 'cpanel', None):
			self.cpanel.progress.stop()
			self.cpanel.runButton.pause()
		self.doHooks('modelStop', [self])
	
	def terminate(self, evt=False):
		self.running = False
		self.hasModel = False
		
		remainder = int(self.t % self.param('updateEvery')) #For some reason this returns a float sometimes?
		if remainder > 0 and getattr(self, 'graph', None) is not None: self.graph.update(self.data.getLast(remainder)) #Last update at the end
		
		if self.param('csv'): self.data.saveCSV(self.param('csv'))
		if getattr(self, 'cpanel', False):
			if getattr(self.cpanel, 'progress', False): self.cpanel.progress.done()
			if getattr(self.cpanel, 'runButton', False): self.cpanel.runButton.terminate()
		elif getattr(self, 'graph', False): self.root.destroy() #Quit if we're in cpanel-less mode
		
		#Re-enable parameters
		for param in self.allParams:
			if param.type=='checkentry' and getattr(param, 'func', None) is not None: continue
			if not param.runtime or (self.graph is None and param.name in ['stopafter', 'csv']): param.enable()
		
		self.doHooks('terminate', [self, self.data.dataframe])
			
	#param is a string (for a global param), a name,object,item,primitive tuple (for per-breed or per-good params), or a list of such
	def paramSweep(self, param, reporters=None):
		import pandas
		if not self.param('stopafter'): raise RuntimeError('Can\'t do a parameter sweep without the value of the \'stopafter\' parameter set')
		
		#Standardize format and get the Param objects
		if not isinstance(param, list): param = [param]
		params = {}
		for p in param:
			if not isinstance(p, tuple): p = (p,)
			pobj = self.parseParamId(p)
			params['-'.join(p)] = (p, pobj)
		
		#Generate the parameter space, a list of dicts
		from itertools import product
		space = [{p[0]:run[k] for k,p in enumerate(params.items())} for run in product(*[p[1].range for p in params.values()])]
		
		#Run the model
		alldata = []
		for i,run in enumerate(space):
			print('Run',str(i+1)+'/'+str(len(space))+':',', '.join([k+'='+('\''+v+'\'' if isinstance(v, str) else str(v)) for k,v in run.items()])+'…')
			for p in self.allParams:
				if not getattr(p, 'config', False): p.reset()
			self.setup()
			for k,v in run.items(): params[k][1].set(v, params[k][0][2] if params[k][1].obj is not None else None)
			
			self.start()
			
			if reporters is not None: data = pandas.DataFrame({k:self.data.all[k] for k in reporters})
			else: data = self.data.dataframe
				
			alldata.append((run, data))
		return alldata
	
	#Creates an unweighted and undirected network of a certain density
	def createNetwork(self, density, kind='edge', prim=None):
		if density < 0 or density > 1: raise ValueError('Network density must take a value between 0 and 1.')
		from itertools import combinations
		agents = self.allagents.values() if prim is None else self.agents[prim]
		for c in combinations(agents, 2):
			if random.randint(0,100) < density*100:
				c[0].newEdge(c[1], kind)
		return self.network(kind, prim)
	
	def network(self, kind='edge', prim=None):
		try:
			import networkx as nx
			G = nx.Graph()
			agents = self.allagents.values() if prim is None else self.agents[prim]
			G.add_nodes_from([a.id for a in agents])
			if kind in self.allEdges:
				G.add_edges_from([(e.vertices[0].id, e.vertices[1].id) for e in self.allEdges[kind]])
		
			return G
		except: warnings.warn('Network export requires Networkx.', None, 2)
		
	def showNetwork(self, kind='edge', prim=None):
		import matplotlib.pyplot as plt, networkx as nx
		G = self.network(kind, prim)
		plt.figure() #New window
		nx.draw(G)
		plt.show()
	
	def spatial(self, *args, **kwargs):
		from helipad.spatial import spatialSetup
		spatialSetup(self, *args, **kwargs)
	
	@property
	def allagents(self):
		agents = {}
		for k, l in self.agents.items():
			agents.update({a.id:a for a in l})
		return agents
	
	#CALLBACK FOR DEFAULT PARAMETERS
	#Model param redundant, strictly speaking, but it's necessary to make the signature match the setter callback
	def nUpdater(self, val, prim, model, force=False):
		if not self.hasModel and not force: return val
		
		if 'num_' in prim: prim = prim.split('_')[1] #Because the parameter callback passes num_{prim}
		array = self.agents[prim]
		diff = val - len(array)

		#Add agents
		if diff > 0:
			maxid = 1
			for a in self.allagents.values():
				if a.id > maxid: maxid = a.id #Figure out maximum existing ID
			for id in range(maxid+1, maxid+int(diff)+1):
				breed = self.doHooks([prim+'DecideBreed', 'decideBreed'], [id, self.primitives[prim].breeds.keys(), self])
				if breed is None: breed = list(self.primitives[prim].breeds.keys())[id%len(self.primitives[prim].breeds)]
				if not breed in self.primitives[prim].breeds:
					raise ValueError('Breed \''+breed+'\' is not registered for the \''+prim+'\' primitive')
				new = self.primitives[prim].class_(breed, id, self)
				array.append(new)
		
		#Remove agents
		elif diff < 0:
			shuffle(array) #Delete agents at random
			
			#Remove agents, maintaining the proportion between breeds
			n = {x: 0 for x in self.primitives[prim].breeds.keys()}
			for a in self.agents[prim]:
				if n[a.breed] < -diff:
					n[a.breed] += 1
					a.die(updateGUI=False)
				else: continue
		
	#
	# DEBUG FUNCTIONS
	# Only call from the console, not in the code
	#
	
	# Requires to be run from Terminal (⌘-⇧-R in TextMate). `self` will refer to the model object
	# Readline doesn't look like it's doing anything here, but it enables certain console features
	# Only works on Mac. Also Gnureadline borks everything, so don't install that.
	def debugConsole(self):
		if sys.platform=='darwin':
			try:
				import code, readline
				vars = globals().copy()
				vars.update(locals())
				shell = code.InteractiveConsole(vars)
				shell.interact()
			except: print('Use pip to install readline and code for a debug console')
	
	#Return agents of a breed if string; return specific agent with ID otherwise
	def agent(self, var, primitive=None):
		if primitive is None: primitive = next(iter(self.primitives))
		if isinstance(var, str):
			return [a for a in self.agents[primitive] if a.breed==var]
		else:
			return self.allagents[var]
		
		return None #If nobody matched
		
	#Returns summary statistics on an agent variable at a single point in time
	def summary(self, var, prim=None, breed=None):
		if prim is None: primitive = next(iter(self.primitives))
		agents = self.agents[prim] if breed is None else self.agent(breed, prim)
		data = pandas.Series([getattr(a, var) for a in agents]) #Pandas gives us nice statistical functions
		stats = {
			'n': data.size,
			'Mean': data.mean(),
			'StDev': data.std(),
			'Variance': data.var(),
			'Maximum': data.max(),
			'Minimum': data.min(),
			'Sum': data.sum()
		}
		for k, v in stats.items():
			print(k+': ', v)

	def launchCpanel(self):
		if not isIpy() and not hasattr(self, 'root'): return
		
		self.doHooks('CpanelPreLaunch', [self])
		
		#Set our agents slider to be a multiple of how many agent types there are
		#Do this down here so we can have breeds registered before determining options
		for k,p in self.primitives.items():
			if self.params['num_'+k].type != 'hidden':
				l = len(p.breeds)
				if not l: continue
				self.params['num_'+k].opts['low'] = makeDivisible(self.params['num_'+k].opts['low'], l, 'max')
				self.params['num_'+k].opts['high'] = makeDivisible(self.params['num_'+k].opts['high'], l, 'max')
				self.params['num_'+k].opts['step'] = makeDivisible(self.params['num_'+k].opts['low'], l, 'max')
				self.params['num_'+k].value = makeDivisible(self.params['num_'+k].value, l, 'max')
				self.params['num_'+k].default = makeDivisible(self.params['num_'+k].default, l, 'max')
		
		try:
			if self.moneyGood is None: self.removePlot('money')
		except: pass #Can't remove plot if re-drawing the cpanel
		
		if not isIpy():
			from helipad.cpanel import Cpanel
			self.cpanel = Cpanel(self.root, self)
			self.debugConsole()
			self.doHooks('CpanelPostInit', [self.cpanel]) #Want the cpanel property to be available here, so don't put in cpanel.py
			self.root.mainloop()		#Launch the control panel
		else:
			from helipad.jupyter import JupyterCpanel, SilentExit
			if getattr(self, 'cpanel', False): self.cpanel.invalidate('Control panel was redrawn in another cell.')
			self.cpanel = JupyterCpanel(self)
			self.doHooks('CpanelPostInit', [self.cpanel])
			raise SilentExit() #Don't blow past the cpanel if doing "run all"
		
		self.doHooks('GUIClose', [self]) #This only executes after all GUI elements have closed
	
	def launchPlots(self):		
		#Trim the plot list to the checked items and sent it to Graph
		plotsToDraw = {k:plot for k,plot in self.plots.items() if plot.selected}
		
		#If there are any graphs to plot
		if not len(plotsToDraw.items()) and (not self.param('stopafter') or not self.param('csv')):
			print('Plotless mode requires stop period and CSV export to be enabled.')
			return
		
		self.doHooks('plotsPreLaunch', [self])
		
		#Start the progress bar
		if getattr(self, 'cpanel', None):
			st = self.param('stopafter')
			self.cpanel.progress.determinate(st and not callable(st))
			self.cpanel.runButton.run()
		
		self.setup()
		
		#If we've got plots, instantiate the Graph object
		title = self.name+(' ' if self.name!='' else '')+'Data Plots'
		if len(plotsToDraw):
			def catchKeypress(event):
				#Toggle legend boxes
				if event.key == 't':
					for plot in self.graph.plots.values():
						leg = plot.axes.get_legend()
						leg.set_visible(not leg.get_visible())
					self.graph.fig.canvas.draw()
			
				#Pause on spacebar
				elif event.key == ' ':
					if self.running: self.stop()
					else: self.start()
			
				#User functions
				self.doHooks('graphKeypress', [event.key, self])
		
			self.graph = Graph(plotsToDraw, title=title)				
			
			self.graph.fig.canvas.mpl_connect('close_event', self.terminate)
			self.graph.fig.canvas.mpl_connect('key_press_event', catchKeypress)
		
		#Otherwise don't allow stopafter to be disabled or we won't have any way to stop the model
		else:
			self.graph = None
			self.params['stopafter'].disable()
			self.params['csv'].disable()
		
		for param in self.allParams:
			if not param.runtime: param.disable() #Disable parameters that can't be changed during runtime
		self.doHooks('plotsLaunch', [self, self.graph])
		
		#If we're running in cpanel-less mode, hook through mainloop so it doesn't exit on pause
		if len(plotsToDraw) and not hasattr(self, 'cpanel') and not isIpy():
			self.root.after(1, self.start)
			self.root.after(1, self.root.withdraw) #Close stray window (don't destroy here)
			self.debugConsole()
			self.root.mainloop()
		else: self.start() #As long as we haven't already started
	
	# Generates function decorators for hooks, reporters, etc.
	def genDecorator(self, todo):
		def dec(name=None, **kwargs):
			if callable(name): func, name, isDec = (name, None, True)
			else: isDec = False
		
			#Is a decorator
			def rep1(fn):
				namn = name #If I do anything with name here, Python throws UnboundLocalError. Possibly a Python bug?
				if namn is None: namn=fn.__name__
				todo(namn, fn, kwargs)
				return fn
			
			return rep1(func) if isDec else rep1
		return dec

class MultiLevel(agent.baseAgent, Helipad):	
	def __init__(self, breed, id, parentModel):
		super().__init__(breed, id, parentModel)
		self.setup()
		self.dontStepAgents = False
	
	def step(self, stage):
		self.dontStepAgents = False
		super().step(stage)

class Shocks:
	def __init__(self, model):
		self.shocks = {}
		self.model = model
		
		class Shock(Item):
			def __init__(self, **kwargs):
				self.boolvar = BooleanVar(value=kwargs['active'])
				del kwargs['active']
				super().__init__(**kwargs)
			
			@property
			def active(self): return self.boolvar.get()
			
			@active.setter
			def active(self, active): self.boolvar.set(active)
			
			def do(self, model):
				if self.param is not None:
					newval = self.valFunc(self.param.get(self.item))	#Pass in current value
					self.param.set(newval, self.item)
					if hasattr(self.param, 'callback') and callable(self.param.callback):
						if self.param.obj is not None and self.item is not None:
							self.param.callback(model, self.param.name, self.item, newval)
						else:
							self.param.callback(model, self.param.name, newval)
				else:
					self.valFunc(model)
		self.Shock = Shock
	
	def __getitem__(self, index): return self.shocks[index]
	def __setitem__(self, index, value): self.shocks[index] = value
	
	#param is the name of the variable to shock.
	#valFunc is a function that takes the current value and returns the new value.
	#timerFunc is a function that takes the current tick value and returns true or false
	#    or the string 'button' in which case it draws a button in the control panel that shocks on press
	#The variable is shocked when timerFunc returns true
	#Can pass in param=None to run an open-ended valFunc that takes the model as an object instead
	def register(self, name, param, valFunc, timerFunc, active=True, desc=None):
		if param is not None:
			item = param[2] if isinstance(param, tuple) and len(param)>2 else None
			param = self.model.parseParamId(param)
		else: item=None
			
		self[name] = self.Shock(
			name=name,
			desc=desc,
			param=param,
			item=item,
			valFunc=valFunc,
			timerFunc=timerFunc,
			active=active
		)
		
	def step(self):
		for name, shock in self.shocks.items():
			if shock.active and callable(shock.timerFunc) and shock.timerFunc(self.model.t):
				shock.do(self.model)
	
	@property
	def number(self): return len(self.shocks)
	
	@property
	def buttons(self): return {k:s for k,s in self.shocks.items() if s.timerFunc=='button'}
	
	@property
	def shocksExceptButtons(self): return {k:s for k,s in self.shocks.items() if callable(s.timerFunc)}
	
	# ===============
	# TIMER FUNCTIONS
	# The following *return* timer functions; they are not themselves timer functions.
	# ===============
	
	#With n% probability each period
	def randn(self, n):
		if n<0 or n>100: raise ValueError('randn() argument can only be between 0 and 100')
		def fn(t): return True if random.randint(0,100) < n else False
		return fn
	
	#Once at t=n. n can be an int or a list of periods
	def atperiod(self, n):
		def fn(t):
			if type(n) == list:
				return True if t in n else False
			else:
				return True if t==n else False
		return fn
	
	#Regularly every n periods
	def everyn(self, n, offset=0):
		def fn(t): return True if t%n-offset==0 else False
		return fn

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)