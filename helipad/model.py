# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========
#
#TODO: Use multiprocessing to run the graphing in a different process

#Make sure we've got the requisite modules
import importlib, sys, warnings
needed = ['pandas', 'matplotlib', 'colour']
for module in needed:
	if importlib.util.find_spec(module) is None:
		print("This model requires "+module+". Please use Pip to install it before continuing.")
		sys.exit()

if importlib.util.find_spec('networkx') is not None:
	import networkx as nx
	hasNx = True

from random import shuffle
from tkinter import *
import pandas
from colour import Color
from numpy import random
# import multiprocessing

#Has to be here so we can invoke TkAgg before Tkinter initializes
#Necessary so Matplotlib doesn't crash Tkinter, even though they don't interact
import matplotlib
matplotlib.use('TkAgg')

from gui import GUI
from data import Data
import agent

#Generic extensible item class to store structured data
class Item():
	def __init__(self, **kwargs):
		for k,v in kwargs.items():
			setattr(self, k, v)

class Helipad():
	def __init__(self):
		# Got to initialize Tkinter first in order for StringVar() and such to work
		self.root = Tk()
		self.root.title('Control Panel')
		self.root.resizable(0,0)
		self.data = Data(self)
		self.shocks = Shocks(self)	
			
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
		for name, label in plotList.items(): self.addPlot(name, label)
		self.defaultPlots = ['prices']
	
	def addPrimitive(self, name, class_, plural=None, dflt=50, low=1, high=100, step=1, hidden=False, priority=100):
		if name=='all': raise ValueError(name+' is a reserved name. Please choose another.')
		if not plural: plural = name+'s'
		class_.primitive = name
		self.primitives[name] = {
			'class': class_,
			'plural': plural,
			'priority': priority,
			'breeds': {},
			'breedParams': {}
		}
		self.addParameter('agents_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step}, callback=self.nUpdater)
		self.agents[name] = []
			
	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, logscale=False):
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
	
	def removePlot(self, name, reassign=None):
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
		if reporter in self.data.reporters and isinstance(self.data.reporters[reporter], tuple):
			for p, f in self.data.reporters[reporter][1].items():
				subkey = reporter+'-'+str(p)+'-pctile'
				subseries.append(subkey)
				self.addSeries(plot, subkey, '', Color('#'+color).lighten(), style='--')

		#Since many series are added at setup time, we have to de-dupe
		for s in self.plots[plot].series:
			if s.reporter == reporter:
				self.plots[plot].series.remove(s)
		
		self.plots[plot].series.append(Item(reporter=reporter, label=label, color=color, style=style, subseries=subseries))
	
	def addButton(self, text, func, desc=None):
		self.buttons.append((text, func, desc))
	
	#Get ready to actually run the model
	def setup(self):
		self.doHooks('modelPreSetup', [self])
		self.t = 0
		
		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point
		
		self.data.reset()
		
		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils', 'agent'))
		# self.data.addReporter('utilityStd', self.data.agentReporter('utils', 'agent', stat='std'))
		
		def pReporter(n, paramType=None, obj=None, prim=None):
			def reporter(model):
				return model.param(n, paramType=paramType, obj=obj, prim=prim)
			return reporter
		
		#Keep track of parameters
		for item, i in self.goods.items():				#Cycle through goods
			for n,p in self.goodParams.items():			#Cycle through parameters
				if p[1]['type'] == 'hidden': continue	#Skip hidden parameters
				self.data.addReporter(n+'-'+item, pReporter(n, paramType='good', obj=item))
		for prim, pdata in self.primitives.items():			#Cycle through primitives
			for breed, i in pdata['breeds'].items():		#Cycle through breeds
				for n,p in pdata['breedParams'].items():	#Cycle through parameters
					if p[1]['type'] == 'hidden': continue	#Skip hidden parameters
					self.data.addReporter(prim+'_'+n+'-'+item, pReporter(n, paramType='breed', obj=breed, prim=prim))
		for n,p in self.params.items():							#Cycle through parameters
			if p[1]['type'] == 'hidden': continue				#Skip hidden parameters
			self.data.addReporter(n, pReporter(n))

		if (self.moneyGood is not None):
			self.data.addReporter('M0', self.data.agentReporter('goods', 'all', good=self.moneyGood, stat='sum'))
			self.addSeries('money', 'M0', 'Monetary Base', self.goods[self.moneyGood].color)
		
		#Per-breed series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in self.primitives['agent']['breeds'].items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', 'agent', breed=breed))
			self.addSeries('utility', 'utility-'+breed, breed.title()+' Utility', b.color)
	
		# Per-good series and reporters
		goods = self.goods.keys()
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
		self.primitives = {k:v for k, v in sorted(self.primitives.items(), key=lambda d: d[1]['priority'])} #Sort by priority
		self.agents = {k: [] for k in self.primitives.keys()} #Clear any surviving agents from last run
		for prim in self.primitives:
			self.nUpdater(self, prim, self.param('agents_'+prim))
		
		self.doHooks('modelPostSetup', [self])
			
	#Adds an adjustable parameter exposed in the config GUI.
	#
	# name (required): A unique internal name for the parameter
	# title (required): A human-readable title for display
	# dflt (required): The default value
	# opts (required): Type-specific options
	
	def addParameter(self, name, title, type, dflt, opts={}, runtime=True, callback=None, paramType=None, desc=None, prim=None):
		if paramType is None: params=self.params
		elif paramType=='breed': params=self.primitives[prim]['breedParams']
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
			keys = self.primitives[prim]['breeds'] if paramType=='breed' else self.goods
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
			if type == 'menu':
				deflt = StringVar()
				deflt.set(opts[dflt])
			elif type == 'check':
				deflt = BooleanVar()
				deflt.set(dflt)
			else:
				deflt = dflt
		
		params[name] = [deflt, {
			'title': title,
			'type': type,
			'dflt': dflt,
			'opts': opts,
			'runtime': runtime,
			'callback': callback,
			'desc': desc
		}]
	
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
			params=self.primitives[prim]['breedParams']
		
		if not name in params:
			if paramType is None: paramType = ''
			warnings.warn(paramType+' Parameter \''+name+'\' does not exist', None, 2)
			return
		
		#Set
		if val is not None:
			if params[name][1]['type'] == 'menu':
				if paramType is None: params[name][0].set(params[name][1]['opts'][val])
				else: params[name][0][obj].set(params[name][1]['opts'][val])
			elif params[name][1]['type'] == 'check':
				if paramType is None: params[name][0].set(val)
				else: params[name][0][obj].set(val)
			else:	
				if paramType is None: params[name][0] = val
				else: params[name][0][obj] = val
		
		#Get
		else:
			if params[name][1]['type'] == 'menu':
				#Flip the k/v of the options dict and return the slug from the full text returned by the menu variable
				flip = {y:x for x,y in params[name][1]['opts'].items()}
				if paramType is None: return flip[params[name][0].get()]							#Basic parameter
				else:
					if obj is None: return {o:flip[v.get()] for o,v in params[name][0].items()}		#Item parameter, item unspecified
					else: return flip[params[name][0][obj].get()]									#Item parameter, item specified
				return flip[fullText]
			elif params[name][1]['type'] == 'check':
				return params[name][0].get() if paramType is None or obj is None else params[name][0][obj].get()
			else:
				return params[name][0] if paramType is None or obj is None else params[name][0][obj]
	
	def breedParam(self, name, breed=None, val=None, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = list(self.primitives.keys())[0]
			else: raise KeyError('Breed parameter must specify which primitive it belongs to')
		return self.param(name, val, paramType='breed', obj=breed, prim=prim)
	
	def goodParam(self, name, good=None, val=None, **kwargs):
		return self.param(name, val, paramType='good', obj=good)
	
	#For adding breeds and goods
	#Should not be called directly
	def addItem(self, obj, name, color, prim=None, **kwargs):
		if obj=='good':
			itemDict = self.goods
			paramDict = self.goodParams
		elif obj=='breed': 
			itemDict = self.primitives[prim]['breeds']
			paramDict = self.primitives[prim]['breedParams']
		else: raise ValueError('addItem obj parameter can only take either \'good\' or \'breed\'');
		
		if name in itemDict:
			warnings.warn(obj+' \''+name+'\' already defined. Overriding…', None, 2)
		
		cobj = Color('#'+color)
		cobj2 = cobj.lighten()
		itemDict[name] = Item(color=cobj, color2=cobj2, **kwargs)
		
		#Make sure the parameter arrays keep up with our items
		for k,p in paramDict.items():
			if isinstance(p[1].dflt, dict):
				if name in p[1].dflt: paramDict[k][0][name] = p[1].dflt[name]	#Forgive out-of-order specification
				elif p[1]['type']=='menu':
					paramDict[k][0][name] = StringVar()
					paramDict[k][0][name].set(p[1]['opts'][next(iter(p[1]['opts']))])	#Choose first item of the list
				elif p[1]['type']=='check': paramDict[k][0][name] = BooleanVar()
				else: paramDict[k][0][name] = 0									#Set to zero
			else:
				paramDict[k][0][name] = paramDict[k][1].dflt
	
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
		g={}
		for k,v in self.goods.items():
			if v.money: continue
			g[k] = v
		return g
			
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
				
	def step(self):
		self.t += 1
		self.doHooks('modelPreStep', [self])
		
		#Reset per-period variables
		#Have to do this all at once at the beginning of the period, not when each agent steps
		for p in self.agents.values():
			for a in p:
				a.currentDemand = {g:0 for g in self.goods.keys()}
				a.currentShortage = {g:0 for g in self.goods.keys()}
		
		self.shocks.step()
		
		#Shuffle or sort agents as necessary
		for prim, lst in self.agents.items():
			if self.order == 'random': shuffle(lst)
			o = self.doHooks([prim+'Order', 'order'], [prim, lst, self])	#Individual and global order hooks 
			if o is not None: self.agents[prim] = o
			
		for self.stage in range(1, self.stages+1):
			self.doHooks('modelStep', [self, self.stage])
			for t in self.agents.values():
				for a in t:
					a.step(self.stage)
		
		self.data.collect(self)
		self.doHooks('modelPostStep', [self])
		return self.t
	
	def network(self, kind='edge', prim=None):
		if not hasNx:
			warnings.warn('Network export requires Networkx.', None, 2)
			return
		
		G = nx.Graph()
		agents = self.allagents.values() if prim is None else self.agents[prim]
		G.add_nodes_from([a.id for a in agents])
		if kind in self.allEdges:
			G.add_edges_from([(e.vertices[0].id, e.vertices[1].id) for e in self.allEdges[kind]])
		
		return G
	
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
				itemDict = self.primitives[prim]['breeds']
				paramDict = self.primitives[prim]['breedParams']
				setget = self.breedParam
			else: raise ValueError('Invalid object type')
			if var in paramDict:
				setget(var, item, newval, prim=prim)
			if 'callback' in paramDict[var][1] and callable(paramDict[var][1]['callback']):
				paramDict[var][1]['callback'](self, var, item, newval)
		else:
			if var in self.params:
				self.param(var, newval)
			if 'callback' in self.params[var][1] and callable(self.params[var][1]['callback']):
				self.params[var][1]['callback'](self, var, newval)
	
	@property
	def allagents(self):
		agents = {}
		for k, l in self.agents.items():
			for a in l:
				agents[a.id] = a
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
				
				breed = self.doHooks([prim+'DecideBreed', 'decideBreed'], [maxid, self.primitives[prim]['breeds'].keys(), self])
				if breed is None: breed = list(self.primitives[prim]['breeds'].keys())[i%len(self.primitives[prim]['breeds'])]
				if not breed in self.primitives[prim]['breeds']:
					raise ValueError('Breed \''+breed+'\' is not registered for the \''+prim+'\' primitive')
				new = self.primitives[prim]['class'](breed, maxid, self)
				array.append(new)
		
		#Remove agents
		elif diff < 0:
			shuffle(array) #Delete agents at random
			
			#Remove agents, maintaining the proportion between breeds
			n = {x: 0 for x in self.primitives[prim]['breeds'].keys()}
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
	def agent(self, var, primitive='agent'):
		if isinstance(var, str):
			agents = []
			for a in self.agents[primitive]:
				if a.breed == var:
					agents.append(a)
			return agents
		else:
			return self.allagents[var]
		
		return None #If nobody matched
		
	#Returns summary statistics on an agent variable at a single point in time
	def summary(self, var, prim='agent', breed=None):
		agents = self.agents['agent'] if breed is None else self.agent(breed, prim)
		data = []
		for a in agents: data.append(getattr(a, var))
		data = pandas.Series(data) #Gives us nice statistical functions
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
		#Callback takes one parameter, model object
		self.doHooks('GUIPreLaunch', [self])
		
		#Blank breeds for any primitives not otherwise specified
		for k,p in self.primitives.items():
			if len(p['breeds'])==0: self.addBreed('', '000000', prim=k)
		
		#Set our agents slider to be a multiple of how many agent types there are
		#Do this down here so we can have breeds registered before determining options
		for k,p in self.primitives.items():
			l = len(p['breeds'])
			self.params['agents_'+k][1]['opts']['low'] = makeDivisible(self.params['agents_'+k][1]['opts']['low'], l, 'max')
			self.params['agents_'+k][1]['opts']['high'] = makeDivisible(self.params['agents_'+k][1]['opts']['high'], l, 'max')
			self.params['agents_'+k][1]['opts']['step'] = makeDivisible(self.params['agents_'+k][1]['opts']['low'], l, 'max')
			self.params['agents_'+k][0] = makeDivisible(self.params['agents_'+k][0], l, 'max')
			self.params['agents_'+k][1]['dflt'] = makeDivisible(self.params['agents_'+k][1]['dflt'], l, 'max')
		
		if self.moneyGood is None:
			for i in ['prices', 'money']:
				del self.plots[i]
				
		self.gui = GUI(self.root, self, headless)
		
		# Debug console
		# Requires to be run from Terminal (⌘-⇧-R in TextMate)
		# Here so that 'self' will refer to the model object
		# Only works on Mac. Also Gnureadline borks everything, so don't install that.
		if sys.platform=='darwin':
			if importlib.util.find_spec("code") is not None and importlib.util.find_spec("readline") is not None:
				import code, readline
				vars = globals().copy()
				vars.update(locals())
				shell = code.InteractiveConsole(vars)
				shell.interact()
			else: print('Use pip to install readline and code for a debug console')
		
		if headless:
			self.root.destroy()
			self.gui.preparePlots()		#Jump straight to the graph
		else: self.root.mainloop()		#Launch the control panel
		
		#Callback takes one parameter, GUI object
		self.doHooks('GUIPostLaunch', [self.gui])

class Shocks():
	def __init__(self, model):
		self.shocks = {}
		self.model = model
	
	def __getitem__(self, index): return self.shocks[index]
	def __setitem__(self, index, value): self.shocks[index] = value
	
	#Var is the name of the variable to shock.
	#valFunc is a function that takes the current value and returns the new value.
	#timerFunc is a function that takes the current tick value and returns true or false
	#    or the string 'button' in which case it draws a button in the control panel that shocks on press
	#The variable is shocked when timerFunc returns true
	#Can pass in var=None to run an open-ended valFunc that takes the model as an object instead
	def register(self, name, var, valFunc, timerFunc, paramType=None, obj=None, prim=None, active=True, desc=None):
		self[name] = {
			'name': name,
			'desc': desc,
			'var': var,
			'valFunc': valFunc,
			'timerFunc': timerFunc,
			'paramType': paramType,
			'obj': obj,
			'prim': prim,
			'active': BooleanVar() #Saves some Tkinter code later
		}
		self[name]['active'].set(active)
		
	def step(self):
		for name, shock in self.shocks.items():
			if shock['active'].get() and callable(shock['timerFunc']) and shock['timerFunc'](self.model.t):
				self.do(name)
	
	def do(self, name):
		shock = self[name]
		if shock['var'] is not None:
			newval = shock['valFunc'](self.model.param(shock['var'], paramType=shock['paramType'], obj=shock['obj'], prim=shock['prim']))	#Pass in current value
		
			if shock['paramType'] is not None and shock['obj'] is not None:
				begin = shock['paramType']
				if shock['prim'] is not None: begin += '_'+shock['prim']
				v=begin+'-'+shock['var']+'-'+shock['obj']
			else: v=shock['var']
			
			self.model.updateVar(v, newval, updateGUI=True)
		else:
			shock['valFunc'](self.model)
	
	@property
	def number(self):
		return len(self.shocks)
	
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