# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========

#Make sure we've got the requisite modules
import importlib, pip, sys, warnings
needed = ['pandas', 'matplotlib', 'colour']
for module in needed:
	if importlib.util.find_spec(module) is None:
		#Can't auto-install as of Pip 10
		print("This model requires "+module+". Please use Pip to install it before continuing.")
		sys.exit()

from random import shuffle
from tkinter import *
from collections import namedtuple
from itertools import combinations
import pandas
from colour import Color
# import multiprocessing

#Has to be here so we can invoke TkAgg before Tkinter initializes
#Necessary so Matplotlib doesn't crash Tkinter, even though they don't interact
import matplotlib
matplotlib.use('TkAgg')

from gui import GUI
from data import Data
from agent import *

Item = namedtuple('Item', ['color', 'color2'])
Series = namedtuple('Series', ['reporter', 'label', 'color', 'style', 'subseries'])
Plot = namedtuple('Plot', ['label', 'series', 'logscale'])

class Helipad():
	def __init__(self):
		# Got to initialize Tkinter first in order for StringVar() and such to work…
		self.root = Tk()
		self.root.title('Control Panel')
		self.root.resizable(0,0)
		self.data = Data(self)
		
		self.params = {}		#Global parameters
		self.breeds = {}		#List of breeds
		self.breedParams = {}	#Per-breed parameters
		self.goods = {}			#List of goods
		self.goodParams = {}	#Per-good parameters
		self.hooks = {}			#External functions to run
		self.buttons = []
		self.shocks = []
		self.stages = 1
		self.order = 'linear'
		self.hasModel = False	#Have we initialized?
		
		#Default parameters
		self.addParameter('agents', 'Number of Agents', 'slider', dflt=50, opts={'low': 1, 'high': 100, 'step': 1}, callback=self.nUpdater)
		self.addParameter('banks', 'Number of Banks', 'slider', dflt=1, opts={'low': 0, 'high': 10, 'step': 1}, callback=self.nUpdater)
		self.addParameter('stores', 'Number of Stores', 'slider', dflt=1, opts={'low': 0, 'high': 10, 'step': 1}, callback=self.nUpdater)
		self.addParameter('M0', 'Base Money Supply', 'hidden', dflt=120000, callback=self.updateM0)
		
		#Plot categories
		self.plots = {}
		plotList = {
			'prices': 'Prices',
			'inventory': 'Inventory',
			'ratios': 'Price ratios',
			'demand': 'Demand',
			'money': 'Money',
			'ngdp': 'NGDP',
			'utility': 'Utility',
			'debt': 'Debt',
			'rr': 'Reserve Ratio',
			'i': 'Interest Rate'
		}
		for name, label in plotList.items(): self.addPlot(name, label, logscale=True if name=='ratios' else False)
		self.defaultPlots = ['prices', 'inventory', 'ratios']
			
	#Position is the number you want it to be, *not* the array position
	def addPlot(self, name, label, position=None, logscale=False):
		plot = Plot(label, [], logscale)
		if position is None: self.plots[name] = plot
		else:		#Reconstruct the dict because there's no insert method...
			newplots, i = ({}, 1)
			for k,v in self.plots.items():
				if position==i: newplots[name] = plot
				newplots[k] = v
				i+=1
			self.plots = newplots
	
	#First arg is the plot it's a part of
	#Second arg is a reporter name registered in DataCollector, or a lambda function
	#Third arg is the series name. Use '' to not show in the legend.
	#Fourth arg is the plot's hex color
	def addSeries(self, plot, reporter, label, color, style='-'):
		if isinstance(color, Color): color = color.hex_l.replace('#','')
		if not plot in self.plots:
			raise KeyError('Plot '+plot+' does not exist. Be sure to register plots before adding series.')
		#Check against columns and not reporters so percentiles work
		if not callable(reporter) and not reporter in self.data.all:
			raise KeyError('Reporter '+reporter+' does not exist. Be sure to register reporters before adding series.')
		
		#Add subsidiary series (e.g. percentile bars)
		subseries = []
		if reporter in self.data.reporters and isinstance(self.data.reporters[reporter], tuple):
			for p, f in self.data.reporters[reporter][1].items():
				subkey = reporter+'-'+str(p)+'-pctile'
				subseries.append(subkey)
				self.addSeries(plot, subkey, '', lighten('#'+color), style='--')

		#Since many series are added at setup time, we have to de-dupe
		for s in self.plots[plot].series:
			if s.reporter == reporter:
				self.plots[plot].series.remove(s)
		
		self.plots[plot].series.append(Series(reporter, label, color, style, subseries))
	
	def addButton(self, text, func):
		self.buttons.append((text, func))
	
	#Get ready to actually run the model
	def setup(self):
		self.doHooks('modelPreSetup', [self])
		self.t = 0
		
		if len(self.breeds)==0: self.addBreed('agent', '000000')
		
		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point
		
		self.data.reset()
		
		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils'))
		# self.data.addReporter('utilityStd', self.data.agentReporter('utils', None, 'std'))
		self.data.addReporter('ngdp', self.data.cbReporter('ngdp'))
		
		def pReporter(n, paramType=None, obj=None):
			def reporter(model):
				return model.param(n, paramType=paramType, obj=obj)
			return reporter
		
		#Keept track of parameters
		for t in ['breed', 'good']:
			for item, i in getattr(self, t+'s').items():				#Cycle through breeds/goods
				for n,p in getattr(self, t+'Params').items():			#Cycle through parameters
					if p[1]['type'] == 'hidden': continue				#Skip hidden parameters
					def reporter(model):
						return model.param(n, paramType=t, obj=item)
					self.data.addReporter(n+'-'+item, pReporter(n, paramType=t, obj=item))
		for n,p in self.params.items():									#Cycle through parameters
			if p[1]['type'] == 'hidden': continue						#Skip hidden parameters
			self.data.addReporter(n, pReporter(n))

		if (self.param('M0') != False):
			self.data.addReporter('M0', self.data.cbReporter('M0'))
			self.data.addReporter('P', self.data.cbReporter('P'))
			self.data.addReporter('storeCash', self.data.storeReporter('balance'))

			self.addSeries('ratios', lambda: 1, '', 'CCCCCC')	#plots ratio of 1 for reference without recording a column of ones
			self.addSeries('money', 'M0', 'Monetary Base', '0000CC')
			self.addSeries('money', 'storeCash', 'Store Cash', '777777')
			self.addSeries('ngdp', 'ngdp', 'NGDP', '000000')
		
		#Per-breed series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in self.breeds.items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', breed))
			self.addSeries('utility', 'utility-'+breed, breed.title()+' Utility', b.color)
	
		# Per-good series and reporters
		goods = []
		for good, g in self.goods.items():
			goods.append(good) #Keep track of this for the combinations below
			self.data.addReporter('inv-'+good, self.data.storeReporter('inventory', good))
			self.data.addReporter('demand-'+good, self.data.storeReporter('lastDemand', good))
			if self.param('M0') != False:
				self.data.addReporter('price-'+good, self.data.storeReporter('price', good))
				self.addSeries('prices', 'price-'+good, good.title()+' Price', g.color)
	
		# Separate from the above to make sure actual values draw above target values
		for good, g in self.goods.items():
			if 'inventory' in self.plots: self.addSeries('inventory', 'inv-'+good, good.title()+' Inventory', g.color)
			if 'demand' in self.plots: self.addSeries('demand', 'demand-'+good, good.title()+' Demand', g.color)
		
		#Don't bother keeping track of the bank-specific variables unless the banking system is there
		if self.param('banks') > 0:
			self.data.addReporter('defaults', self.data.bankReporter('defaultTotal'))
			self.data.addReporter('debt', self.data.bankReporter('loans'))
			self.data.addReporter('reserveRatio', self.data.bankReporter('reserveRatio'))
			self.data.addReporter('targetRR', self.data.bankReporter('targetRR'))
			self.data.addReporter('i', self.data.bankReporter('i'))
			self.data.addReporter('r', self.data.bankReporter('realInterest'))
			self.data.addReporter('inflation', self.data.bankReporter('inflation'))
			self.data.addReporter('withdrawals', self.data.bankReporter('lastWithdrawal'))
			self.data.addReporter('M2', self.data.cbReporter('M2'))

			self.addSeries('money', 'defaults', 'Defaults', 'CC0000')
			self.addSeries('money', 'M2', 'Money Supply', '000000')
			self.addSeries('debt', 'debt', 'Outstanding Debt', '000000')
			self.addSeries('rr', 'targetRR', 'Target', '777777')
			self.addSeries('rr', 'reserveRatio', 'Reserve Ratio', '000000')
			self.addSeries('i', 'i', 'Nominal interest', '000000')
			self.addSeries('i', 'r', 'Real interest', '0000CC')
			self.addSeries('i', 'inflation', 'Inflation', 'CC0000')
		
		#Price ratios, color halfway between
		if (self.param('M0') != False):
			for r in combinations(goods, 2):
				self.data.addReporter('ratio-'+r[0]+'-'+r[1], self.data.ratioReporter(r[0], r[1]))
				c1, c2 = self.goods[r[0]].color, self.goods[r[1]].color
				c3 = Color(red=(c1.red+c2.red)/2, green=(c1.green+c2.green)/2, blue=(c1.blue+c2.blue)/2)
				self.addSeries('ratios', 'ratio-'+r[0]+'-'+r[1], r[0].title()+'/'+r[1].title()+' Ratio', c3)
				
		self.hasModel = True #Declare before instantiating agents
		
		#Initialize agents
		self.banks = []
		self.stores = []
		self.agents = []
		self.nUpdater(self, 'banks', self.param('banks'))
		self.nUpdater(self, 'stores', self.param('stores'))
		self.cb = CentralBank(0, self)
		self.nUpdater(self, 'agents', self.param('agents'))
		
		self.doHooks('modelPostSetup', [self])
			
	#Adds an adjustable parameter exposed in the config GUI.
	#
	# name (required): A unique internal name for the parameter
	# title (required): A human-readable title for display
	# dflt (required): The default value
	# opts (required): Type-specific options
	
	def addParameter(self, name, title, type, dflt, opts={}, runtime=True, callback=None, paramType=None, desc=None):
		if paramType is None: params=self.params
		elif paramType=='breed': params=self.breedParams
		elif paramType=='good': params=self.goodParams
		else: raise ValueError('Invalid object '+paramType)
		
		if name in params: warnings.warn('Parameter \''+name+'\' already defined. Overriding...', None, 2)
		
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
			keys = self.breeds if paramType=='breed' else self.goods
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
	
	def addBreedParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None):
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc)
	
	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None):
		self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc)
	
	#Get or set a parameter, depending on whether there are two or three arguments
	#Everything past the third argument is for internal use only
	def param(self, name, val=None, paramType=None, obj=None):
		if paramType is None:		params=self.params
		elif paramType=='breed':	params=self.breedParams
		elif paramType=='good':		params=self.goodParams
		
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
	
	def breedParam(self, name, breed=None, val=None):
		return self.param(name, val, paramType='breed', obj=breed)
	
	def goodParam(self, name, good=None, val=None):
		return self.param(name, val, paramType='good', obj=good)
	
	#For adding breeds and goods
	#Should not be called directly
	def addItem(self, obj, name, color):
		itemDict = getattr(self, obj+'s')
		paramDict = getattr(self, obj+'Params')
		
		if name in itemDict:
			warnings.warn(obj+' \''+name+'\' already defined. Overriding...', None, 2)
		
		cobj = Color('#'+color)
		cobj2 = lighten('#'+color)
		itemDict[name] = Item(cobj, cobj2)
		
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
	
	def addBreed(self, name, color):
		self.addItem('breed', name, color)
		
	def addGood(self, name, color):
		self.addItem('good', name, color)
			
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
	
	#Var is the name of the variable to shock.
	#valFunc is a function that takes the current value and returns the new value.
	#timerFunc is a function that takes the current tick value and returns true or false
	#The variable is shocked when timerFunc returns true
	def registerShock(self, var, valFunc, timerFunc, paramType=None, obj=None):
		self.shocks.append({
			'var': var,
			'valFunc': valFunc,
			'timerFunc': timerFunc,
			'paramType': paramType,
			'obj': obj
		})		
				
	def step(self):
		self.t += 1
		self.doHooks('modelPreStep', [self])
		
		#Shock variables at the beginning of the period
		for shock in self.shocks:
			if shock['timerFunc'](self.t):
				newval = shock['valFunc'](self.param(shock['var'], paramType=shock['paramType'], obj=shock['obj']))	#Pass in current value
				
				if shock['paramType'] is not None and shock['obj'] is not None: v=shock['paramType']+'-'+shock['var']+'-'+shock['obj']
				else: v=shock['var']
					
				self.updateVar(v, newval, updateGUI=True)
				# print("Period",self.t,"shocking",shock['var'],"to",newval)
		
		types = ['agents', 'stores', 'banks']
		
		#Shuffle or sort agents as necessary
		for t in types:
			if self.order == 'random': shuffle(getattr(self, t))
			o = self.doHooks([t+'Order', 'order'], [getattr(self, t), self])	#Individual and global order hooks 
			if o is not None: setattr(self, t, o)
			
		for self.stage in range(1, self.stages+1):
			self.doHooks('modelStep', [self, self.stage])
			for t in types:
				for a in getattr(self, t):
					a.step(self.stage)
			self.cb.step(self.stage)					#Step the central bank last
		
		self.data.collect(self)
		self.doHooks('modelPostStep', [self])
		return self.t
	
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
			itemDict = getattr(self, obj+'s')
			paramDict = getattr(self, obj+'Params')
			setget = getattr(self, obj+'Param')
			if var in paramDict:
				setget(var, item, newval)
			if 'callback' in paramDict[var][1] and callable(paramDict[var][1]['callback']):
				paramDict[var][1]['callback'](self, var, item, newval)
		else:
			if var in self.params and var != 'M0':
				self.param(var, newval)
			if 'callback' in self.params[var][1] and callable(self.params[var][1]['callback']):
				self.params[var][1]['callback'](self, var, newval)
	
	@property
	def allagents(self):
		agents = {}
		for a in self.agents + self.stores + self.banks:
			agents[a.unique_id] = a
		return agents
	
	# CALLBACKS FOR DEFAULT PARAMETERS
	
	def updateM0(self, model, var, val):
		if self.hasModel and var == 'M0':
			self.cb.M0 = val
	
	def nUpdater(self, model, var, val):
		if not self.hasModel: return
		array = getattr(self, var)
		diff = val - len(array)

		#Add agents
		if diff > 0:
			maxid = 1
			for id, a in self.allagents.items():
				if a.unique_id > maxid: maxid = a.unique_id #Figure out maximum existing ID
			for i in range(0, int(diff)):
				maxid += 1
				if var == 'agents':
					if 'decideBreed' in self.hooks:
						breed = self.doHooks('decideBreed', [maxid, self])
						if not breed in self.breeds: raise ValueError('Breed '+breed+' has not been registered')
					else: breed = list(self.breeds.keys())[i%len(self.breeds)]
					new = hAgent(breed, maxid, self)
				elif var == 'banks': new = Bank(maxid, self)
				elif var == 'stores': new = Store(maxid, self)
				array.append(new)

		elif diff < 0:
			shuffle(array) #Delete agents at random
			
			#Remove agents, maintaining the proportion between breeds
			if var=='agents': 
				n = {}
				for x in self.breeds: n[x]=0
				for a in self.agents:
					if n[a.breed] < -diff:
						n[a.breed] += 1
						a.die()
					else: continue
			
			else:
				for i in range(-diff):
					array[-1].die()
		
	#
	# DEBUG FUNCTIONS
	# Only call from the console, not in the code
	#
	
	#Return agents of a type if string; return specific agent with ID otherwise
	def agent(self, var):
		if isinstance(var, str):
			agents = []
			for a in self.agents:
				if a.breed == var:
					agents.append(a)
			return agents
			
		else:
			for a in self.agents:
				if a.unique_id == var:
					return a
		
		return None #If nobody matched
		
	#Returns summary statistics on an agent variable at a single point in time
	def summary(self, var, type=False):
		agents = self.agents if not type else self.agent(type)
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

	def launchGUI(self):
		#Callback takes one parameter, model object
		self.doHooks('GUIPreLaunch', [self])
		
		#Set our agents slider to be a multiple of how many agent types there are
		#Do this down here so we can have breeds registered before determining options
		l = len(self.breeds)
		if (l==0): #Make explicit breed declaration optional
			self.addBreed('agent', '000000')
			l=1
		self.params['agents'][1]['opts'] = {'low': l, 'high': 100*l, 'step': l}
		self.params['agents'][0] = 50*l
		self.params['agents'][1]['dflt'] = 50*l
		
		if self.param('M0') == False:
			for i in ['prices', 'ratios', 'money','debt','rr','i','ngdp']:
				del self.plots[i]
				
		self.gui = GUI(self.root, self)
		
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
			
		self.root.mainloop()
		
		#Callback takes one parameter, GUI object
		self.doHooks('GUIPostLaunch', [self.gui])

#Takes a hex color *with* the #
def lighten(color):
	c = Color(color)
	c2 = Color(hue=c.hue, saturation=c.saturation, luminance=.66+c.luminance/3)
	return c2.hex_l.replace('#','')
	