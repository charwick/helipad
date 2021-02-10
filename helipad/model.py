# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========

import sys, warnings, pandas, asyncio, time
from random import shuffle, choice
from numpy import random

from helipad.visualize import BaseVisualization
from helipad.helpers import *
from helipad.param import *
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
		self.events = {}
		self.stages = 1
		self.order = 'linear'
		self.hasModel = False	#Have we initialized?
		self.moneyGood = None
		self.timer = False
		self.visual = None
		
		#Default parameters
		self.addPrimitive('agent', agent.Agent, dflt=50, low=1, high=100)
		
		#Decorators
		def repdec(name, fn, kwargs): self.data.addReporter(name, fn, **kwargs)
		def hookdec(name, fn, kwargs): self.addHook(name, fn, **kwargs)
		def buttondec(name, fn, kwargs): self.addButton(name, fn, **kwargs)
		def eventdec(name, fn, kwargs): self.addEvent(name, fn, **kwargs)
		self.reporter = self.genDecorator(repdec)
		self.hook = self.genDecorator(hookdec)
		self.button = self.genDecorator(buttondec)
		self.event = self.genDecorator(eventdec)
		
		#A few things that only make sense to do if it's the topmost model
		if not hasattr(self, 'breed'):
			
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
			self.addParameter('refresh', 'Refresh Every __ Periods', 'slider', 20, opts=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], runtime=True, config=True)
			self.addParameter('shocks', 'Shocks', 'checkgrid', opts={}, dflt={}, runtime=True, config=True)
		
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
		if isinstance(name, list): return [self.removePrimitive(n) for n in name]
		if not name in self.primitives: return False
		del self.primitives[name]
		del self.agents[name]
		del self.params['num_'+name]
		return True
		
	#Deprecated in Helipad 1.2 and moved to TimeSeries.plots
	#Remove in Helipad 1.4
	@property
	def plots(self):
		warnings.warn('model.plots is deprecated and will be removed in a future version. The list of TimeSeries plots can be accessed with model.visual.plots.', None, 2)
		from helipad.visualize import TimeSeries
		if not isinstance(self.visual, TimeSeries): self.useVisual(TimeSeries)
		return self.visual.plots
	
	#Deprecated in Helipad 1.2 in favor of TimeSeries.addPlot()
	#To be removed in Helipad 1.4
	def addPlot(self, name, label, position=None, selected=True, logscale=False, stack=False):
		from helipad.visualize import TimeSeries
		
		warnings.warn('model.addPlot() is deprecated and will be removed in a future version. Specify model.useVisual(TimeSeries) and use TimeSeries.addPlot() instead.', None, 2)
		if not isinstance(self.visual, TimeSeries):
			self.useVisual(TimeSeries)
			warnings.warn('Visualization must be explicitly specified. Adding TimeSeries for compatibility…', None, 2)
		
		return self.visual.addPlot(name, label, position, selected, logscale, stack)
	
	#Deprecated in Helipad 1.2 in favor of TimeSeries.addPlot()
	#To be removed in Helipad 1.4
	def removePlot(self, name, reassign=None):
		from helipad.visualize import TimeSeries
		warnings.warn('model.removePlot() is deprecated and will be removed in a future version. Specify model.useVisual(TimeSeries) and use TimeSeries.removePlot() instead.', None, 2)
		if isinstance(self.visual, TimeSeries): return self.visual.removePlot(name, reassign)
	
	#Deprecated in Helipad 1.2 in favor of Plot.addSeries()
	#To be removed in Helipad 1.4
	def addSeries(self, plot, reporter, label, color, style='-'):
		warnings.warn('model.addSeries() is deprecated and will be removed in a future version. Use Plot.addSeries() instead.', None, 2)
		return self.plots[plot].addSeries(reporter, label, color, style)
	
	def addButton(self, text, func, desc=None):
		self.shocks.register(text, None, func, 'button', True, desc)
			
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
		return params[name]
	
	def addBreedParam(self, name, title, type, dflt, opts={}, prim=None, runtime=True, callback=None, desc=None, getter=None, setter=None):
		if prim is None:
			if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		return self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc, prim=prim, getter=getter, setter=setter)
	
	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None, getter=None, setter=None):
		return self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc, getter=getter, setter=setter)
	
	#Get or set a parameter, depending on whether there are two or three arguments
	def param(self, param, val=None):
		
		#Deprecated in Helipad 1.2, remove in Helipad 1.4
		if param=='stopafter' and callable(val):
			warnings.warn('Setting the \'stopafter\' parameter to a function is deprecated and will be removed in a future version. Use model.addEvent() and set \'stopafter\' to the event name instead.', None, 2)
			self.addEvent(val.__name__, val)
			val = val.__name__
		
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
			
			#Add the M0 plot once we have a money good
			if (self.visual is None or self.visual.isNull) and hasattr(self.visual, 'plots'):
				try:
					if not 'money' in self.visual.plots: self.visual.addPlot('money', 'Money', selected=False)
				except: pass #Can't add plot if re-drawing the cpanel
		
		#Add demand and shortage plots once we have at least 2 goods
		if len(self.goods) == 1 and (self.visual is None or self.visual.isNull) and hasattr(self.visual, 'plots'):
			try:
				if not 'demand' in self.visual.plots: self.visual.addPlot('demand', 'Demand', selected=False)
				if not 'shortages' in self.visual.plots: self.visual.addPlot('shortage', 'Shortages', selected=False)
			except: pass
			
		return self.addItem('good', name, color, endowment=endowment, money=money)
	
	@property
	def nonMoneyGoods(self):
		return {k:v for k,v in self.goods.items() if not v.money}
			
	def addHook(self, place, func, prioritize=False):
		if not place in self.hooks: self.hooks[place] = []
		if prioritize: self.hooks[place].insert(0, func)
		else: self.hooks[place].append(func)
	
	def removeHook(self, place, fname, removeall=False):
		if not place in self.hooks: return False
		if isinstance(fname, list): return [self.removeHook(place, f, removeall) for f in fname]
		did = False
		for h in self.hooks[place]:
			if h.__name__ == fname:
				self.hooks[place].remove(h)
				if not removeall: return True
				else: did = True
		return did
	
	def clearHooks(self, place):
		if isinstance(place, list): return [self.clearHooks(p) for p in place]
		if not place in self.hooks or not len(self.hooks[place]): return False
		self.hooks[place].clear()
		return True
	
	#Returns the value of the last function in the list
	def doHooks(self, place, args):
		#Take a list of hooks; go until we get a response
		if isinstance(place, list):
			for f in place:
				r = self.doHooks(f, args)
				if r is not None: return r
			return None
		
		deprec = {
			'graphUpdate':'visualRefresh',	#1.2; can be removed in 1.4
			'plotsLaunch':'visualLaunch'	#1.2; can be removed in 1.4
		}
		if place in deprec:
			warnings.warn('The '+place+' hook is deprecated and will be removed in a future version. Please use the '+deprec[place]+' hook instead.', None, 2)
			place = deprec[place]
		
		if not place in self.hooks: return None
		for f in self.hooks[place]: r = f(*args)
		return r
	
	def addEvent(self, name, fn, **kwargs):
		self.events[name] = Event(name, fn, **kwargs)
		return self.events[name]
	
	def removeEvent(self, name):
		if not name in self.events: return False
		del self.events[name]
		return True
	
	def clearEvents(self): self.events.clear()
	
	def useVisual(self, viz):
		if hasattr(self, 'breed'):
			warnings.warn('Visualizations can only be registered on the top-level model.', None, 2)
			return #Doesn't matter if it's not the top-level model
		
		if viz is not None and not issubclass(viz, BaseVisualization):
			raise RuntimeError('Visualization class must inherit from BaseVisualization.')
		
		self.visual = viz(self) if viz is not None else None
		return self.visual
	
	#Get ready to actually run the model
	def setup(self):
		if self.hasModel: self.terminate()
		self.doHooks('modelPreSetup', [self])
		self.t = 0
		
		#Blank breeds for any primitives not otherwise specified
		for k,p in self.primitives.items():
			if len(p.breeds)==0: self.addBreed('', '#000000', prim=k)
		
		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point
		
		self.data.reset()
		for e in self.events.values(): e.reset()
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
			if self.visual is not None and hasattr(self.visual, 'plots') and 'money' in self.visual.plots:
				self.visual.plots['money'].addSeries('M0', 'Monetary Base', self.goods[self.moneyGood].color)
		
		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils', defPrim))
		
		#Per-breed and per-good series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in next(iter(self.primitives.values())).breeds.items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', defPrim, breed=breed))
			if self.visual is not None and self.visual.__class__.__name__=='TimeSeries':
				self.visual.plots['utility'].addSeries('utility-'+breed, breed.title()+' Utility', b.color)
	
		if len(self.goods) >= 2:
			for good, g in self.nonMoneyGoods.items():
				self.data.addReporter('demand-'+good, self.data.agentReporter('currentDemand', 'all', good=good, stat='sum'))
				self.data.addReporter('shortage-'+good, self.data.agentReporter('currentShortage', 'all', good=good, stat='sum'))
				if self.visual is not None and hasattr(self.visual, 'plots'):
					if 'demand' in self.visual.plots: self.visual.plots['demand'].addSeries('demand-'+good, good.title()+' Demand', g.color)
					if 'shortage' in self.visual.plots: self.visual.plots['shortage'].addSeries('shortage-'+good, good.title()+' Shortage', g.color)
		
		#Initialize agents
		self.primitives = {k:v for k, v in sorted(self.primitives.items(), key=lambda d: d[1].priority)}	#Sort by priority
		pops = {prim: self.param('num_'+prim) for prim in self.primitives.keys()}
		for ags in self.agents.values(): ags.clear()														#Clear any surviving agents from last run
		for prim in self.primitives: self.nUpdater(pops[prim], prim, self, force=True)						#Force is so we can call nupdater before instantiating hasModel
		
		#Start progress bar
		#Put this here and not in .start() because it'll flash on unpause otherwise
		if getattr(self, 'cpanel', None):
			st = self.param('stopafter')
			self.cpanel.progress.determinate(st and isinstance(st, int))
		
		for param in self.allParams:
			if not param.runtime: param.disable() #Disable parameters that can't be changed during runtime
		
		self.hasModel = True
		self.doHooks('modelPostSetup', [self])
				
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
		for e in self.events.values():
			if (not e.triggered or e.repeat) and e.check(self) and self.visual is not None and e.name!=self.param('stopafter'):
				self.visual.event(self.t, **e.kwargs)
		self.doHooks('modelPostStep', [self])
		return self.t
	
	#This is split out as an async function to allow user input while running the loop in Jupyter
	async def run(self):
		if self.timer:
			begin = time.time()
		while self.running:
			t = self.step()
			st = self.param('stopafter')
			
			if t%self.param('refresh')==0:
				if self.timer: t2 = time.time()
				
				if getattr(self, 'cpanel', False) and st and isinstance(st, int): self.cpanel.progress.update(t/st)
				
				#Update graph
				if self.visual is not None and not self.visual.isNull:
					await asyncio.sleep(0.001) #Listen for keyboard input
					data = self.data.getLast(t - self.visual.lastUpdate)
	
					self.visual.update(data)
					self.visual.lastUpdate = t
				
					self.doHooks('visualRefresh', [self, self.visual]) 
				
				elif getattr(self, 'cpanel', None):
					if isIpy(): await asyncio.sleep(0.001) #Listen for keyboard input
					else: self.cpanel.parent.update() #Make sure we don't hang the interface if plotless
			
				# Performance indicator
				if self.timer:
					newtime = time.time()
					print('Period', t, ':', round(self.param('refresh')/(newtime-begin),2), 'periods/second (',round((t2-begin)/(newtime-begin)*100,2),'% model, ',round((newtime-t2)/(newtime-begin)*100,2),'% visuals)')
					begin = newtime
	
			if st:
				stop = self.events[st].triggered if isinstance(st, str) else t>=st
				if stop: self.terminate()
	
	#The *args allows it to be used as an Ipywidgets callback
	def start(self, *args):
		
		#Start the progress bar
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
			if not isIpy(): asyncio.run(self.run())	#If Tkinter, it needs an event loop
			else: asyncio.ensure_future(self.run()) #If Jupyter, it already has an event loop
	
	def stop(self, *args):
		self.running = False
		if getattr(self, 'cpanel', None):
			self.cpanel.progress.stop()
			self.cpanel.runButton.pause()
		self.doHooks('modelStop', [self])
	
	def terminate(self, evt=False):
		if not self.hasModel: return
		self.running = False
		self.hasModel = False
		if self.visual is not None: self.visual.terminate(self) #Clean up visualizations
		
		remainder = int(self.t % self.param('refresh')) #For some reason this returns a float sometimes?
		if remainder > 0 and self.visual is not None: self.visual.update(self.data.getLast(remainder)) #Last update at the end
		
		if self.param('csv'): self.data.saveCSV(self.param('csv'))
		if getattr(self, 'cpanel', False):
			self.cpanel.progress.done()
			self.cpanel.runButton.terminate()
		elif getattr(self, 'visual', False) and getattr(self, 'root', False): self.root.destroy() #Quit if we're in cpanel-less mode
		
		#Re-enable parameters
		for param in self.allParams:
			if param.type=='checkentry' and param.event: continue
			if not param.runtime: param.enable()
		
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
		
		#For backward-compatibility with pre-1.2 paramSweep results.
		#Can be removed and replaced with Item in Helipad 1.4
		class Result(Item):
			def __getitem__(self, index):
				warnings.warn('Parameter sweep results are now an object, not a tuple. Access by numeric index is deprecated and will be removed in a future version.', None, 2)
				if index==0: return self.vars
				elif index==1: return self.data
		
		#Run the model
		alldata = []
		for i,run in enumerate(space):
			print('Run',str(i+1)+'/'+str(len(space))+':',', '.join([k+'='+('\''+v+'\'' if isinstance(v, str) else str(v)) for k,v in run.items()])+'…')
			for p in self.allParams:
				if not getattr(p, 'config', False): p.reset()
			
			for k,v in run.items(): params[k][1].set(v, params[k][0][2] if params[k][1].obj is not None else None)
			self.setup()
			self.start()
			
			if reporters is not None: data = pandas.DataFrame({k:self.data.all[k] for k in reporters})
			else: data = self.data.dataframe
			
			events = [Result(name=e.name, triggered=e.triggered, data=e.data) for e in self.events.values()]
				
			alldata.append(Item(vars=run, data=data, events=events))
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
		try: import networkx as nx
		except: warnings.warn('Network export requires Networkx.', None, 2)
		
		#Have to use DiGraph in order to draw any arrows
		G = nx.DiGraph(name=kind)
		agents = self.allagents.values() if prim is None else self.agents[prim]
		G.add_nodes_from([(a.id, {'breed': a.breed, 'primitive': a.primitive}) for a in agents])
		ae = self.allEdges
		if kind in ae:
			for e in ae[kind]: G.add_edge(
				e.startpoint.id if e.directed else e.vertices[0].id,
				e.endpoint.id if e.directed else e.vertices[1].id,
				weight=e.weight, directed=e.directed
			)
		return G
	
	@property
	def allEdges(self):
		es = {}
		for a in self.allagents.values():
			for e in a.alledges:
				if not e.kind in es: es[e.kind] = []
				if not e in es[e.kind]: es[e.kind].append(e)
		return es
	
	def spatial(self, *args, **kwargs):
		from helipad.spatial import spatialSetup
		return spatialSetup(self, *args, **kwargs)
	
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
	# Only call from the console, not in user code
	#
	
	# Requires to be run from Terminal (⌘-⇧-R in TextMate). `self` will refer to the model object
	# Readline doesn't look like it's doing anything here, but it enables certain console features
	# Only works on Mac. Also Gnureadline borks everything, so don't install that.
	# Has to be called *after* Cpanel.__init__() is called, or the cpanel object won't be available.
	def debugConsole(self):
		if sys.platform=='darwin':
			try:
				import code, readline
				vars = globals().copy()
				vars['self'] = self
				shell = code.InteractiveConsole(vars)
				shell.interact()
			except: print('Use pip to install readline and code for a debug console')
	
	#Return agents of a breed if string; return specific agent with ID otherwise
	def agent(self, var, primitive=None):
		if primitive is None: primitive = next(iter(self.primitives))
		if isinstance(var, str):
			return [a for a in self.agents[primitive] if a.breed==var]
		else:
			aa = self.allagents
			return aa[var] if var in aa else None
		
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
		if hasattr(self, 'breed'): warnings.warn('Control panel can only be launched on the top-level model.', None, 2)
		
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
		
		if not isIpy():
			from helipad.cpanelTkinter import Cpanel
			self.cpanel = Cpanel(self)
			self.debugConsole()
			self.doHooks('CpanelPostInit', [self.cpanel]) #Want the cpanel property to be available here, so don't put in cpanel.py
			self.cpanel.parent.mainloop()		#Launch the control panel
		else:
			from helipad.cpanelJupyter import Cpanel, SilentExit
			if getattr(self, 'cpanel', False): self.cpanel.invalidate('Control panel was redrawn in another cell.')
			self.cpanel = Cpanel(self)
			self.doHooks('CpanelPostInit', [self.cpanel])
			raise SilentExit() #Don't blow past the cpanel if doing "run all"
		
		self.doHooks('GUIClose', [self]) #This only executes after all GUI elements have closed
	
	def launchVisual(self):
		if self.visual is None or self.visual.isNull:
			if not getattr(self, 'cpanel', False):
				print('No visualizations available. To run the model with no GUI, use model.start() instead.')
				return
			if not self.param('stopafter') or not self.param('csv'):
				print('Running from the control panel with no visualization requires stop period and CSV export to be enabled.')
				return
		
		self.setup()
		
		if self.visual is not None and not self.visual.isNull:
			self.visual.launch(self.name+(' ' if self.name!='' else '')+'Data Plots')
		else:
			self.params['stopafter'].disable()
			self.params['csv'].disable()
		
		self.doHooks('visualLaunch', [self, self.visual])
		
		#If we're running in cpanel-less mode, hook through a Tkinter loop so it doesn't exit on pause
		if not hasattr(self, 'cpanel') and not self.visual.isNull and not isIpy():
			from tkinter import Tk
			self.root = Tk()
			self.root.after(1, self.start)
			self.root.after(1, self.root.withdraw) #Close stray window (don't destroy here)
			self.debugConsole()
			self.root.mainloop()
		else: self.start() #As long as we haven't already started
	
	def launchPlots(self):
		warnings.warn('model.launchPlots() is deprecated. Use model.launchVisual() instead.', None, 2)
		self.launchVisual()
	
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

class Event:
	def __init__(self, name, trigger, repeat=False, **kwargs):
		self.name = name
		self.trigger = trigger
		self.repeat = repeat
		self.kwargs = kwargs
		self.data = []
		self.triggered = []
		self.reset()
	
	def check(self, model):
		if self.triggered and not self.repeat: return False
		if (isinstance(self.trigger, int) and model.t==self.trigger) or (callable(self.trigger) and self.trigger(model)):
			data = {k: v[0] for k,v in model.data.getLast(1).items()}
			if self.repeat:
				self.data.append(data)
				self.triggered.append(model.t)
			else:
				self.data = data
				self.triggered = model.t
			return True
	
	def reset(self):
		if self.repeat:
			self.data.clear()
			self.triggered.clear()
		else:
			self.data = None
			self.triggered = False

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)