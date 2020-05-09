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
from numpy import random
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
	def addPlot(self, name, label, position=None, logscale=False, selected=True):
		plot = Item(label=label, series=[], logscale=logscale)
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
				subseries.append(subkey)
				self.addSeries(plot, subkey, '', Color('#'+color).lighten(), style='--')

		#Since many series are added at setup time, we have to de-dupe
		for s in self.plots[plot].series:
			if s.reporter == reporter:
				self.plots[plot].series.remove(s)
		
		series = Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries, plot=plot)
		self.plots[plot].series.append(series)
		if reporter in self.data.reporters: self.data.reporters[reporter].series.append(series)
	
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
		
		def pReporter(n, paramType=None, obj=None, prim=None):
			def reporter(model):
				return model.param(n, paramType=paramType, obj=obj, prim=prim)
			return reporter
		
		#Add reporters for all parameters
		for item, i in self.goods.items():				#Cycle through goods
			for n,p in self.goodParams.items():			#Cycle through parameters
				if p.type == 'hidden': continue			#Skip hidden parameters
				self.data.addReporter(n+'-'+item, pReporter(n, paramType='good', obj=item))
		for prim, pdata in self.primitives.items():		#Cycle through primitives
			for breed, i in pdata.breeds.items():		#Cycle through breeds
				for n,p in pdata.breedParams.items():	#Cycle through parameters
					if p.type == 'hidden': continue		#Skip hidden parameters
					self.data.addReporter(prim+'_'+n+'-'+item, pReporter(n, paramType='breed', obj=breed, prim=prim))
		for n,p in self.params.items():					#Cycle through parameters
			if p.type == 'hidden': continue				#Skip hidden parameters
			self.data.addReporter(n, pReporter(n))

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
		
		#Instantiate the defaults.
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
	
		if paramType is not None:
			keys = self.primitives[prim].breeds if paramType=='breed' else self.goods
			if type == 'menu':
				deflt = {b:StringVar() for b in keys}
				if isinstance(dflt, dict):
					for k in deflt: deflt[k].set(opts[dflt[k]])
					for b in keys:
						if not b in deflt: deflt[k].set('') #Make sure we've got all the breeds in the array
				else:
					for k in deflt: deflt[k].set(opts[dflt]) #Set to opts[dflt] rather than dflt because OptionMenu deals in the whole string
			elif type == 'check':
				deflt = {b:BooleanVar() for b in keys}
				if isinstance(dflt, dict):
					for k in deflt: deflt[k].set(opts[dflt[k]])
					for b in keys:
						if not b in deflt: deflt[k].set(False) #Make sure we've got all the breeds in the array
				else:
					for k in deflt: deflt[k].set(dflt)
			else:
				deflt = {b:dflt for b in keys}
				#No 'else' because the dict already contains default values if it's a per-breed universal slider
				if isinstance(dflt, dict):
					for k in deflt: deflt[k] = dflt[k] if k in dflt else 0
				else:
					for b in keys:
						if not b in deflt: deflt[k] = None  #Make sure we've got all the breeds in the array
				
		else:
			if type == 'menu': deflt = StringVar(value=opts[dflt])
			elif type == 'check': deflt = BooleanVar(value=dflt)
			else: deflt = dflt
		
		params[name] = Item(
			value=deflt,
			title=title,
			type=type,
			dflt=dflt,
			opts=opts,
			runtime=runtime,
			callback=callback,
			desc=desc
		)
	
	def addBreedParam(self, name, title, type, dflt, opts={}, prim=None, runtime=True, callback=None, desc=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc, prim=prim)
	
	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None):
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc)
	
	#Get or set a parameter, depending on whether there are two or three arguments
	#Everything past the third argument is for internal use only
	def param(self, name, val=None, paramType=None, obj=None, prim=None):
		if paramType is None:		params=self.params
		elif paramType=='good':		params=self.goodParams
		elif paramType=='breed':
			if prim is None:
				if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
				else: raise KeyError('Breed parameter must specify which primitive it belongs to')
			params=self.primitives[prim].breedParams
		
		if not name in params:
			if paramType is None: paramType = ''
			warnings.warn(paramType+' Parameter \''+name+'\' does not exist', None, 2)
			return
		
		#Set
		if val is not None:
			if params[name].type == 'menu':
				if paramType is None: params[name][0].set(params[name].opts[val])
				else: params[name].value[obj].set(params[name].opts[val])
			elif params[name].type == 'check':
				if paramType is None: params[name].value.set(val)
				else: params[name].value[obj].set(val)
			else:	
				if paramType is None: params[name].value = val
				else: params[name].value[obj] = val
		
		#Get
		else:
			if params[name].type == 'menu':
				#Flip the k/v of the options dict and return the slug from the full text returned by the menu variable
				flip = {y:x for x,y in params[name].opts.items()}
				if paramType is None: return flip[params[name].value.get()]							#Global parameter
				else:
					if obj is None: return {o:flip[v.get()] for o,v in params[name].value.items()}	#Item parameter, item unspecified
					else: return flip[params[name].value[obj].get()]								#Item parameter, item specified
				return flip[fullText]
			elif params[name].type == 'check':
				return params[name].value.get() if paramType is None or obj is None else params[name].value[obj].get()
			else:
				v = params[name].value if paramType is None or obj is None else params[name].value[obj]
				#Have sliders with an int step value return an int
				if params[name].opts is not None and 'step' in params[name].opts and isinstance(params[name].opts['step'], int): v = int(v)
				return v
	
	def breedParam(self, name, breed=None, val=None, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		return self.param(name, val, paramType='breed', obj=breed, prim=prim)
	
	def goodParam(self, name, good=None, val=None, **kwargs):
		return self.param(name, val, paramType='good', obj=good)
	
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
		
		#Make sure the parameter arrays keep up with our items
		for k,p in paramDict.items():
			if isinstance(p.dflt, dict):
				if name in p.dflt: p.value[name] = p.dflt[name]	#Forgive out-of-order specification
				elif p.type=='menu':
					p.value[name] = StringVar()
					p.value[name].set(p.opts[next(iter(p.opts))])	#Choose first item of the list
				elif p.type=='check': p.value[name] = BooleanVar()
				else: p.value[name] = 0									#Set to zero
			else:
				p.value[name] = p.dflt
	
	def addBreed(self, name, color, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
			else: raise KeyError('Breed must specify which primitive it belongs to')
		self.addItem('breed', name, color, prim=prim)
		
	def addGood(self, name, color, endowment=None, money=False):
		if money:
			if self.moneyGood is not None: print('Money good already specified as',self.moneyGood,'. Overriding…')
			self.moneyGood = name
		self.addItem('good', name, color, endowment=endowment, money=money)
	
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
		import matplotlib.pyplot as plt
		G = self.network(kind, prim)
		plt.figure() #New window
		nx.draw(G)
		plt.show()
	
	#For receiving updated values from the GUI
	#Update the model parameter and execute the callback if it exists
	#updateGUI is false if receiving values from the GUI; true if sending values to the GUI (e.g. shocks)
	def updateVar(self, var, newval, updateGUI=False):
		
		#Makes sure changes are reflected in the sliders
		#Checkboxes and menus update regardless of the updateGUI setting
		if updateGUI and var in self.gui.sliders and hasattr(self.gui.sliders[var], 'set'):
			self.gui.sliders[var].set(newval)
		
		if '-' in var:
			#Names like obj-var-item, i.e. good-prod-axe
			obj, var, item = var.split('-')	#Per-object variables
			if '_' in obj: obj, prim = obj.split('_')
			else: prim = None
			
			if obj == 'good':
				itemDict = self.goods
				paramDict = self.goodParams
				setget = self.goodParam
			elif obj == 'breed':
				itemDict = self.primitives[prim].breeds
				paramDict = self.primitives[prim].breedParams
				setget = self.breedParam
			else: raise ValueError('Invalid object type')
			if var in paramDict:
				setget(var, item, newval, prim=prim)
			if hasattr(paramDict[var], 'callback') and callable(paramDict[var].callback):
				paramDict[var].callback(self, var, item, newval)
		else:
			if var in self.params:
				self.param(var, newval)
			if hasattr(self.params[var], 'callback') and callable(self.params[var].callback):
				self.params[var].callback(self, var, newval)
	
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
				self.params['agents_'+k].dflt = makeDivisible(self.params['agents_'+k].dflt, l, 'max')
		
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
		
		self.doHooks('GUIPostLaunch', [self.gui])

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
				if self.var is not None:
					newval = self.valFunc(model.param(self.var, paramType=self.paramType, obj=self.obj, prim=self.prim))	#Pass in current value
		
					if self.paramType is not None and self.obj is not None:
						begin = self.paramType
						if self.prim is not None: begin += '_'+self.prim
						v=begin+'-'+self.var+'-'+self.obj
					else: v=self.var
			
					model.updateVar(v, newval, updateGUI=True)
				else:
					self.valFunc(model)
		self.Shock = Shock
	
	def __getitem__(self, index): return self.shocks[index]
	def __setitem__(self, index, value): self.shocks[index] = value
	
	#Var is the name of the variable to shock.
	#valFunc is a function that takes the current value and returns the new value.
	#timerFunc is a function that takes the current tick value and returns true or false
	#    or the string 'button' in which case it draws a button in the control panel that shocks on press
	#The variable is shocked when timerFunc returns true
	#Can pass in var=None to run an open-ended valFunc that takes the model as an object instead
	def register(self, name, var, valFunc, timerFunc, paramType=None, obj=None, prim=None, active=True, desc=None):
		self[name] = self.Shock(
			name=name,
			desc=desc,
			var=var,
			valFunc=valFunc,
			timerFunc=timerFunc,
			paramType=paramType,
			obj=obj,
			prim=prim,
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

#Append to the Color class
def lighten(self):
	return Color(hue=self.hue, saturation=self.saturation, luminance=.66+self.luminance/3)
Color.lighten = lighten

def makeDivisible(n, div, c='min'):
	return n-n%div if c=='min' else n+(div-n%div if n%div!=0 else 0)