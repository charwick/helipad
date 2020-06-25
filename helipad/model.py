# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========
#
#TODO: Use multiprocessing to run the graphing in a different process

import sys, warnings, pandas
from random import shuffle, choice
from tkinter import *
from colour import Color
from numpy import random, arange
# import multiprocessing

#Has to be here so we can invoke TkAgg before Tkinter initializes
#Necessary so Matplotlib doesn't crash Tkinter, even though they don't interact
import matplotlib
matplotlib.use('TkAgg')

#Generic extensible item class to store structured data
class Item():
	def __init__(self, **kwargs):
		for k,v in kwargs.items():
			setattr(self, k, v)

from helipad.gui import GUI
from helipad.data import Data
import helipad.agent as agent

class Helipad():
	runInit = True #for multiple inheritance
	
	def __init__(self):
		
		#Got to initialize Tkinter first in order for StringVar() and such to work
		#But only do so if it's the top-most model
		if not hasattr(self, 'breed'): self.root = Tk()
		
		self.data = Data(self)
		self.shocks = Shocks(self)	
		
		self.name = ''
		self.agents = {}
		self.primitives = {}
		self.params = {}		#Global parameters
		self.goods = {}			#List of goods
		self.goodParams = {}	#Per-good parameters
		self.hooks = {}			#External functions to run
		self.buttons = []
		self.stages = 1
		self.order = 'linear'
		self.hasModel = False	#Have we initialized?
		self.moneyGood = None
		self.allEdges = {}
		
		#Default parameters
		self.addPrimitive('agent', agent.Agent, dflt=50, low=1, high=100)
		
		#Plot categories
		self.plots = {}
		plotList = {
			'prices': 'Prices',
			'demand': 'Demand',
			'shortage': 'Shortages',
			'money': 'Money',
			'utility': 'Utility'
		}
		for name, label in plotList.items(): self.addPlot(name, label, selected=False)
		self.defaultPlots = []
		
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
		self.addParameter('agents_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step} if not hidden else None, callback=self.nUpdater)
		self.agents[name] = []
	
	def removePrimitive(self, name):
		del self.primitives[name]
		del self.agents[name]
		del self.params['agents_'+name]
		
	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, selected=True, logscale=False, stack=False):
		plot = Item(label=label, series=[], logscale=logscale, stack=stack)
		if position is None or position > len(self.plots):
			self.plots[name] = plot
		else:		#Reconstruct the dict because there's no insert method…
			newplots, i = ({}, 1)
			for k,v in self.plots.items():
				if position==i: newplots[name] = plot
				newplots[k] = v
				i+=1
			self.plots = newplots
		
		if selected: self.defaultPlots.append(name)
		return plot
	
	def removePlot(self, name, reassign=None):
		if hasattr(self, 'GUI'): raise RuntimeError('Cannot remove plots after control panel is drawn')
		if isinstance(name, list):
			for p in name: self.removePlot(p, reassign)
			return
				
		if reassign is not None:
			self.plots[reassign].series += self.plots[name].series
		del self.plots[name]
	
	#First arg is the plot it's a part of
	#Second arg is a reporter name registered in DataCollector, or a lambda function
	#Third arg is the series name. Use '' to not show in the legend.
	#Fourth arg is the plot's hex color, or a Color object
	def addSeries(self, plot, reporter, label, color, style='-'):
		if isinstance(color, Color): color = color.hex_l.replace('#','')
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
				subseries.append(self.addSeries(plot, subkey, '', Color('#'+color).lighten(), style='--'))

		#Since many series are added at setup time, we have to de-dupe
		for s in self.plots[plot].series:
			if s.reporter == reporter:
				self.plots[plot].series.remove(s)
		
		series = Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=plot)
		self.plots[plot].series.append(series)
		if reporter in self.data.reporters: self.data.reporters[reporter].series.append(series)
		return series
	
	def addButton(self, text, func, desc=None):
		self.buttons.append((text, func, desc))
	
	#Get ready to actually run the model
	def setup(self):
		self.doHooks('modelPreSetup', [self])
		self.t = 0
		
		#Blank breeds for any primitives not otherwise specified
		for k,p in self.primitives.items():
			if len(p.breeds)==0: self.addBreed('', '000000', prim=k)
		
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
			if p.type == 'hidden': continue				#Skip hidden parameters
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
				if 'store' in self.primitives and self.moneyGood is not None:
					self.data.addReporter('price-'+good, self.data.agentReporter('price', 'store', good=good))
					self.addSeries('prices', 'price-'+good, good.title()+' Price', g.color)
	
		self.hasModel = True #Declare before instantiating agents
		
		#Initialize agents
		self.primitives = {k:v for k, v in sorted(self.primitives.items(), key=lambda d: d[1].priority)} #Sort by priority
		self.agents = {k: [] for k in self.primitives.keys()} #Clear any surviving agents from last run
		for prim in self.primitives:
			self.nUpdater(self, prim, self.param('agents_'+prim))
		
		self.doHooks('modelPostSetup', [self])
			
	#Registers an adjustable parameter exposed in the config GUI.	
	def addParameter(self, name, title, type, dflt, opts={}, runtime=True, callback=None, paramType=None, desc=None, prim=None):
		if paramType is None: params=self.params
		elif paramType=='breed': params=self.primitives[prim].breedParams
		elif paramType=='good': params=self.goodParams
		else: raise ValueError('Invalid object \''+paramType+'\'')
		
		if name in params: warnings.warn('Parameter \''+name+'\' already defined. Overriding…', None, 2)
		
		args = {
			'name': name,
			'title': title,
			'type': type,
			'default': dflt,
			'opts': opts,
			'runtime': runtime,
			'callback': callback,
			'desc': desc,
			'obj': paramType
		}
		if paramType is not None:
			args['keys'] = self.primitives[prim].breeds if paramType=='breed' else self.goods
		
		params[name] = Param(**args)
	
	def addBreedParam(self, name, title, type, dflt, opts={}, prim=None, runtime=True, callback=None, desc=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc, prim=prim)
	
	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None):
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc)
	
	#Get or set a parameter, depending on whether there are two or three arguments
	def param(self, param, val=None):
		item = param[2] if isinstance(param, tuple) and len(param)>2 else None
		param = self.parseParamId(param)
		
		if val is not None: param.set(val, item)
		else: return param.get(item)
	
	@property
	def allParams(self):
		params = list(self.params.values())+list(self.goodParams.values())
		for p in self.primitives.values(): params += list(p.breedParams.values())
		return params
	
	#Parses a parameter identifier tuple and returns a Param object
	#For internal use only
	def parseParamId(self, p):
		if not isinstance(p, tuple): p = (p,)
		if len(p)==1:		return self.params[p[0]]
		elif p[1]=='good':	return self.goodParams[p[0]]
		elif p[1]=='breed':
			if len(p)<4 or p[3] is None:
				if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
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
		
		cobj = Color('#'+color)
		cobj2 = cobj.lighten()
		itemDict[name] = Item(color=cobj, color2=cobj2, **kwargs)
		
		#Make sure the parameter lists keep up with our items
		for k,p in paramDict.items(): p.addKey(name)
		
		return itemDict[name]
	
	def addBreed(self, name, color, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
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
			
	def addHook(self, place, func):
		if not place in self.hooks: self.hooks[place] = []
		self.hooks[place].append(func)
	
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
	
	#type='breed' or 'good', item is the breed or good name, prim is the primitive if type=='breed'
	#t can also be a function taking the model object with a finishing condition
	#param is a string (for a global param), a name,object,item,primitive tuple (for per-breed or per-good params), or a list of such
	def paramSweep(self, param, t, reporters=None):
		import pandas
		
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
			for p in self.allParams: p.reset()
			self.setup()
			for k,v in run.items(): params[k][1].set(v, params[k][0][2] if params[k][1].obj is not None else None)
			
			if callable(t):
				while not t(self): now = self.step()
			else:
				for i in range(t): now = self.step()
			
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
	
	@property
	def allagents(self):
		agents = {}
		for k, l in self.agents.items():
			agents.update({a.id:a for a in l})
		return agents
	
	#CALLBACK FOR DEFAULT PARAMETERS
	#Model param redundant, strictly speaking, but it's necessary to make the signature match the other callbacks, where it is necessary
	def nUpdater(self, model, prim, val):
		if not self.hasModel: return
		
		if 'agents_' in prim: prim = prim.split('_')[1] #Because updateVar will pass agents_{prim}
		array = self.agents[prim]
		diff = val - len(array)

		#Add agents
		if diff > 0:
			maxid = 1
			for id, a in self.allagents.items():
				if a.id > maxid: maxid = a.id #Figure out maximum existing ID
			for i in range(0, int(diff)):
				maxid += 1
				
				breed = self.doHooks([prim+'DecideBreed', 'decideBreed'], [maxid, self.primitives[prim].breeds.keys(), self])
				if breed is None: breed = list(self.primitives[prim].breeds.keys())[i%len(self.primitives[prim].breeds)]
				if not breed in self.primitives[prim].breeds:
					raise ValueError('Breed \''+breed+'\' is not registered for the \''+prim+'\' primitive')
				new = self.primitives[prim].class_(breed, maxid, self)
				array.append(new)
		
		#Remove agents
		elif diff < 0:
			shuffle(array) #Delete agents at random
			
			#Remove agents, maintaining the proportion between breeds
			n = {x: 0 for x in self.primitives[prim].breeds.keys()}
			for a in self.agents[prim]:
				if n[a.breed] < -diff:
					n[a.breed] += 1
					a.die()
				else: continue
		
	#
	# DEBUG FUNCTIONS
	# Only call from the console, not in the code
	#
	
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
			
	#
	# And, last but not least, the GUI init
	#

	def launchGUI(self, headless=False):
		if not hasattr(self, 'root'): return
		
		self.doHooks('GUIPreLaunch', [self])
		
		#Set our agents slider to be a multiple of how many agent types there are
		#Do this down here so we can have breeds registered before determining options
		for k,p in self.primitives.items():
			if self.params['agents_'+k].type != 'hidden':
				l = len(p.breeds)
				if not l: continue
				self.params['agents_'+k].opts['low'] = makeDivisible(self.params['agents_'+k].opts['low'], l, 'max')
				self.params['agents_'+k].opts['high'] = makeDivisible(self.params['agents_'+k].opts['high'], l, 'max')
				self.params['agents_'+k].opts['step'] = makeDivisible(self.params['agents_'+k].opts['low'], l, 'max')
				self.params['agents_'+k].value = makeDivisible(self.params['agents_'+k].value, l, 'max')
				self.params['agents_'+k].default = makeDivisible(self.params['agents_'+k].default, l, 'max')
		
		if self.moneyGood is None:
			for i in ['prices', 'money']:
				del self.plots[i]
				
		self.gui = GUI(self.root, self, headless)
		
		# Debug console
		# Requires to be run from Terminal (⌘-⇧-R in TextMate)
		# Here so that 'self' will refer to the model object
		# Readline doesn't look like it's doing anything here, but it enables certain console features
		# Only works on Mac. Also Gnureadline borks everything, so don't install that.
		if sys.platform=='darwin':
			try:
				import code, readline
				vars = globals().copy()
				vars.update(locals())
				shell = code.InteractiveConsole(vars)
				shell.interact()
			except: print('Use pip to install readline and code for a debug console')
		
		self.root.title(self.name+(' ' if self.name!='' else '')+'Control Panel')
		self.root.resizable(0,0)
		if headless:
			self.root.destroy()
			self.gui.preparePlots()		#Jump straight to the graph
		else: self.root.mainloop()		#Launch the control panel
		
		self.doHooks('GUIClose', [self]) #This only executes after all GUI elements have closed

class MultiLevel(agent.baseAgent, Helipad):	
	def __init__(self, breed, id, parentModel):
		super().__init__(breed, id, parentModel)
		self.setup()
		self.dontStepAgents = False
	
	def step(self, stage):
		self.dontStepAgents = False
		super().step(stage)

class Shocks():
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

class Param(Item):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		
		#Instantiate the objects once, because we don't want to overwrite them
		if self.obj is not None:
			if self.type=='menu': self.value = {b:StringVar() for b in self.keys}
			elif self.type=='check': self.value = {b:BooleanVar() for b in self.keys}
		else:
			if self.type == 'menu': self.value = StringVar()
			elif self.type == 'check': self.value = BooleanVar()
		
		self.reset() #Populate with default values
	
	#Instantiate the value dict from the default value.
	#1. Are we dealing with a per-breed or a global default?
	#1a. If per-breed, is the default universal or breed-specific?
	#2. Do we have a menu, a check, or a slider?
	#
	#Per-breed universal menu:		str → dict{StringVar}
	#Per-breed universal check:		bool → dict{BooleanVar}
	#Per-breed universal slider:	int → dict{int}
	#Per-breed specific menu:		dict{str} → dict{StringVar}
	#Per-breed specific check:		dict{bool} → dict{BooleanVar}
	#Per-breed specific slider:		dict{int} → dict{int}
	#Global menu:					str → StringVar
	#Global check:					bool → BooleanVar
	#Global slider:					int → int
	def reset(self):
		if self.obj is not None:
			if self.type=='menu':
				if isinstance(self.default, dict):
					for k,v in self.value.items(): v.set(self.opts[self.default[k]])
					for b in self.keys:
						if not b in self.default: self.value[b].set('') #Make sure we've got all the items in the array
				else:
					#Set to opts[self.default] rather than self.default because OptionMenu deals in the whole string
					for k,v in self.value.items(): v.set(self.opts[self.default])
			elif self.type=='check':
				if isinstance(self.default, dict):
					for k,v in self.value.items(): v.set(self.opts[self.default[k]])
					for b in self.keys:
						if not b in self.value: self.value[b].set(False) #Make sure we've got all the breeds in the array
				else:
					for k in self.value: self.value[k].set(self.default)
			else:
				if isinstance(self.default, dict):
					self.value = {k:self.default[k] if k in self.default else 0 for k in self.keys}
				else:
					self.value = {k:self.default for k in self.keys}
		else:
			if self.type == 'menu': self.value.set(self.opts[self.default])
			elif self.type == 'check': self.value.set(self.default)
			else: self.value = self.default
	
	def set(self, val, item=None, updateGUI=True):
		if self.obj is not None and item is None: raise KeyError('A '+self.obj+' whose parameter value to set must be specified')
		if self.type == 'menu':
			if self.obj is None: self.value.set(self.opts[val])
			else: self.value[item].set(self.opts[val])
		elif self.type == 'check':
			if self.obj is None: self.value.set(val)
			else: self.value[item].set(val)
		else:
			if self.obj is None:
				self.value = val
				if updateGUI and hasattr(self, 'element'): self.element.set(val)
			else:
				self.value[item] = val
				if updateGUI and hasattr(self, 'element'): self.element[item].set(val)
	
	#Return a bool|str|num for a global parameter or a per-object parameter if the item is specified
	#Otherwise return dict{str:bool|str|num} with all the items
	def get(self, item=None):
		if self.type == 'menu':
			#Flip the k/v of the options dict and return the slug from the full text returned by the menu variable
			flip = {y:x for x,y in self.opts.items()}
			if self.obj is None: return flip[self.value.get()]								#Global parameter
			else:
				if item is None: return {o:flip[v.get()] for o,v in self.value.items()}		#Item parameter, item unspecified
				else: return flip[self.value[item].get()]									#Item parameter, item specified
		elif self.type == 'check':
			return self.value.get() if self.obj is None or item is None else self.value[item].get()
		else:
			v = self.value if self.obj is None or item is None else self.value[item]
			#Have sliders with an int step value return an int
			if self.opts is not None and 'step' in self.opts and isinstance(self.opts['step'], int): v = int(v)
			return v
	
	@property
	def range(self):
		if self.type=='check': return [False, True]
		elif self.type=='menu': return self.opts.keys()
		elif self.type=='slider':
			values = arange(self.opts['low'], self.opts['high'], self.opts['step']).tolist()
			values.append(self.opts['high']) #arange doesn't include the high
			return values
	
	#If a breed or good gets added after the parameter instantiation, we want to be able to keep up
	def addKey(self, key):
		if self.obj is None: print('Can\'t add keys to a global parameter…')
		else:
			if isinstance(self.default, dict):
				if key in self.default: self.value[key] = self.default[key]	#Forgive out-of-order specification
				elif self.type=='menu':
					self.value[key] = StringVar()
					self.value[key].set(self.opts[next(iter(self.opts))])	#Choose first item of the list
				elif self.type=='check': self.value[key] = BooleanVar()
				else: self.value[key] = 0									#Set to zero
			else:
				self.value[key] = self.default

#Append to the Color class
def lighten(self):
	return Color(hue=self.hue, saturation=self.saturation, luminance=.66+self.luminance/3)
Color.lighten = lighten

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)