# ==========
# Basic model infrastructure
# Do not run this file; import it and run your file.
# ==========

import os, sys, warnings, asyncio, time
import gettext
import pandas
from random import shuffle, choice
from numpy import random

from helipad.visualize import BaseVisualization, Charts, TimeSeries
from helipad.helpers import *
from helipad.param import Params, Shocks
from helipad.data import Data
from helipad.agent import Agent, baseAgent

class Helipad:
	runInit = True #for multiple inheritance. Has to be a static property

	def __init__(self, locale='en'):
		#Have to do this first so that _() is available early
		if not hasattr(self, 'breed'):
			gettext.translation('helipad', localedir=os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))+'/locales', languages=[locale]).install()

		self.data = Data(self)
		self.params = Params(self)
		self.shocks = Shocks(self)
		self.events = Events()
		self.hooks = Hooks()
		self.primitives = Primitives(self)
		self.goods = Goods(self)				#List of goods

		self.name = ''
		self.agents = {}
		self.stages = 1
		self.order = 'linear'
		self.hasModel = False		#Have we initialized?
		self.timer = False
		self.visual = None
		self.cpanel = None

		self.running = False
		self._cut = False

		#Default parameters
		self.primitives.add('agent', Agent, dflt=50, low=1, high=100)

		#Decorators
		def repdec(name, fn, kwargs): self.data.addReporter(name, fn, **kwargs)
		def hookdec(name, fn, kwargs): self.hooks.add(name, fn, **kwargs)
		def buttondec(name, fn, kwargs): self.addButton(name, fn, **kwargs)
		def eventdec(name, fn, kwargs): self.events.add(name, fn, **kwargs)
		self.reporter = self.genDecorator(repdec)
		self.hook = self.genDecorator(hookdec)
		self.button = self.genDecorator(buttondec)
		self.event = self.genDecorator(eventdec)

		#A few things that only make sense to do if it's the topmost model
		if not hasattr(self, 'breed'):

			#Privileged parameters
			#Toggle the progress bar between determinate and indeterminate when stopafter gets changed
			def switchPbar(model, name, val):
				if not model.hasModel or not model.cpanel or not getattr(model.cpanel, 'progress', False): return
				if not val: model.cpanel.progress.determinate(False)
				else:
					model.cpanel.progress.determinate(True)
					model.cpanel.progress.update(model.t/val)
			self.params.add('stopafter', _('Stop on period'), 'checkentry', False, runtime=True, config=True, entryType='int', callback=switchPbar)
			self.params.add('csv', _('CSV?'), 'checkentry', False, runtime=True, config=True)
			self.params.add('refresh', _('Refresh Every __ Periods'), 'slider', 20, opts=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], runtime=True, config=True)
			self.params['shocks'] = self.shocks

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
					print(_('A Helipad update is available! Use `pip install -U helipad` to upgrade to version {}.').format(available[0]))
			except: pass #Fail silently if we're not online

	def addButton(self, text, func, desc=None):
		self.shocks.add(text, None, func, 'button', True, desc)

	#Get or set a parameter, depending on whether there are two or three arguments
	def param(self, param, val=None):
		item = param[2] if isinstance(param, tuple) and len(param)>2 else None
		param = self.params[param[0]] if isinstance(param, tuple) else self.params[param]

		if val is not None: param.set(val, item)
		else: return param.get(item)

	def addBreed(self, name, color, prim=None):
		if prim is None:
			if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
			else: raise KeyError(_('Breed must specify which primitive it belongs to.'))
		return self.primitives[prim].breeds.add(name, color)

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

	def useVisual(self, viz):
		if hasattr(self, 'breed'):
			warnings.warn(_('Visualizations can only be registered on the top-level model.'), None, 2)
			return #Doesn't matter if it's not the top-level model

		if viz is not None and not issubclass(viz, BaseVisualization):
			raise RuntimeError(_('Visualization class must inherit from BaseVisualization.'))

		self.visual = viz(self) if viz is not None else None
		return self.visual

	#Get ready to actually run the model
	def setup(self):
		if self.hasModel: self.terminate()
		self.doHooks('modelPreSetup', [self])
		self.t = 0

		#Blank breeds for any primitives not otherwise specified
		for k,p in self.primitives.items():
			if not p.breeds: p.breeds.add('', '#000000')

		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point

		self.data.reset()
		for e in self.events.values(): e.reset()
		defPrim = 'agent' if 'agent' in self.primitives else next(iter(self.primitives))

		def pReporter(param, item=None):
			def reporter(model): return param.get(item)
			return reporter

		#Add reporters for parameters
		for n,p in self.params.items():
			if p.type == 'hidden' or getattr(p, 'config', False): continue	#Skip hidden and config parameters
			if p.per is None: self.data.addReporter(n, pReporter(p))
			elif p.per == 'good':
				for good in p.pKeys:
					self.data.addReporter(n+'-'+good, pReporter(p, good))
			elif p.per == 'breed':
				for breed in p.pKeys:
					self.data.addReporter(p.prim+'-'+n+'-'+breed, pReporter(p, breed))

		if self.goods.money is not None:
			self.data.addReporter('M0', self.data.agentReporter('stocks', 'all', good=self.goods.money, stat='sum'))
			if self.visual is not None and isinstance(self.visual, TimeSeries) and hasattr(self.visual, 'plots') and 'money' in self.visual.plots:
				self.visual.plots['money'].addSeries('M0', _('Monetary Base'), self.goods[self.goods.money].color)

		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils', defPrim))

		#Per-breed and per-good series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in self.primitives[defPrim].breeds.items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', defPrim, breed=breed))
			if self.visual is not None and self.visual.__class__.__name__=='TimeSeries':
				self.visual.plots['utility'].addSeries('utility-'+breed, breed.title()+' '+_('Utility'), b.color)

		if len(self.goods) >= 2:
			for good, g in self.goods.nonmonetary.items():
				self.data.addReporter('demand-'+good, self.data.agentReporter('currentDemand', 'all', good=good, stat='sum'))
				if self.visual is not None and hasattr(self.visual, 'plots'):
					if 'demand' in self.visual.plots: self.visual.plots['demand'].addSeries('demand-'+good, good.title()+' '+_('Demand'), g.color)

		#Initialize agents
		self.primitives = dict(sorted(self.primitives.items(), key=lambda d: d[1].priority))				#Sort by priority
		pops = {prim: self.param('num_'+prim) for prim in self.primitives}
		for ags in self.agents.values(): ags.clear()														#Clear any surviving agents from last run
		for prim in self.primitives: self.nUpdater(pops[prim], prim, self, force=True)						#Force is so we can call nupdater before instantiating hasModel

		#Start progress bar
		#Put this here and not in .start() because it'll flash on unpause otherwise
		if self.cpanel:
			st = self.param('stopafter')
			self.cpanel.progress.determinate(st and isinstance(st, int))

		for param in self.params.values():
			if not param.runtime: param.disable() #Disable parameters that can't be changed during runtime

		#Patch our async functions for compatibility with Spyder's event loop
		if isIpy() and not isNotebook():
			try:
				import nest_asyncio
				nest_asyncio.apply()
			except:
				raise ImportError(_('nest_asyncio is required to run Helipad from Spyder.'))

		self.hasModel = True
		self.doHooks('modelPostSetup', [self])

	def cutStep(self): self._cut = True

	def step(self, stage=1):
		self.t += 1
		self.doHooks('modelPreStep', [self])

		#Reset per-period variables
		#Have to do this all at once at the beginning of the period, not when each agent steps
		for p in self.agents.values():
			for a in p: a.currentDemand = {g:0 for g in self.goods}

		self.shocks.step()

		def sortFunc(model, stage, func):
			def sf(agent): return func(agent, model, stage)
			return sf

		for self.stage in range(1, self.stages+1):
			self._cut = False
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

				#Keep the agent list constant for a given loop because modifying it while looping
				#(e.g. if an agent dies or reproduces) will screw up the looping
				agentpool = self.agents[prim].copy()

				#Matching model
				if 'match' in order:
					matchN = order.split('-')
					matchN = int(matchN[1]) if len(matchN) > 1 else 2
					matchpool = self.agents[prim].copy()
					while len(matchpool) > len(agentpool) % matchN and not self._cut:
						agents = []
						for a in range(matchN):
							agent = choice(matchpool)
							matchpool.remove(agent)
							agents.append(agent)

							#Allow selection of matches, but only on the first agent
							if a==0:
								others = self.doHooks('matchSelect', [agent, matchpool, self, self.stage])
								if others is not None:
									if (isinstance(others, baseAgent) and matchN==2): others = [others]
									if (isinstance(others, list) and len(others)==matchN-1):
										for other in others: matchpool.remove(other)
										agents += others
										break
									else: raise ValueError(_('matchSelect did not return the correct number of agents.'))

						accept = self.doHooks('matchAccept', agents)
						if accept is not None and not accept:
							matchpool = agents + matchpool #Prepend agents to decrease the likelihood of a repeat matching
							continue
						for a in agents: agent.step(self.stage)
						self.doHooks([prim+'Match', 'match'], [agents, prim, self, self.stage])

					#Step any remainder agents
					for agent in matchpool:
						if not self._cut: agent.step(self.stage)

				#Activation model
				else:
					for a in agentpool:
						if not self._cut: a.step(self.stage)

		self.data.collect(self)
		for e in self.events.values():
			if (not e.triggered or e.repeat) and e.check(self) and self.visual is not None and not self.visual.isNull and e.name!=self.param('stopafter'):
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
				if self.cpanel and st and isinstance(st, int): self.cpanel.progress.update(t/st)

				#Update graph
				if self.visual is not None and not self.visual.isNull:
					await asyncio.sleep(0.001) #Listen for keyboard input
					data = self.data.getLast(t - self.visual.lastUpdate)

					self.visual.update(data)
					self.visual.lastUpdate = t

					self.doHooks('visualRefresh', [self, self.visual])

				elif self.cpanel:
					if isNotebook(): await asyncio.sleep(0.001) #Listen for keyboard input
					else: self.cpanel.update() #Make sure we don't hang the interface if plotless

				# Performance indicator
				if self.timer:
					newtime = time.time()
					print(_('Period {0}: {1} periods/second ({2}% model, {3}% visuals)').format(t, round(self.param('refresh')/(newtime-begin),2), round((t2-begin)/(newtime-begin)*100,2), round((newtime-t2)/(newtime-begin)*100,2)))
					begin = newtime

			if st:
				stop = self.events[st].triggered if isinstance(st, str) else t>=st
				if stop: self.terminate()

	#The *args allows it to be used as an Ipywidgets callback
	def start(self, *args):

		#Start the progress bar
		if self.cpanel:
			self.cpanel.progress.start()
			self.cpanel.runButton.run()

		self.doHooks('modelStart', [self, self.hasModel])
		if not self.hasModel: self.setup()
		self.running = True

		if isNotebook(): asyncio.ensure_future(self.run()) #If Jupyter, it already has an event loop
		else: asyncio.run(self.run())	#If Tkinter, it needs an event loop

	def stop(self, *args):
		self.running = False
		if self.cpanel:
			self.cpanel.progress.stop()
			self.cpanel.runButton.pause()
		self.doHooks('modelStop', [self])

	def terminate(self, evt=False):
		if not self.hasModel: return
		self.running = False
		self.hasModel = False
		if self.visual is not None: self.visual.terminate(self) #Clean up visualizations

		remainder = int(self.t % self.param('refresh')) #For some reason this returns a float sometimes?
		if remainder > 0 and self.visual is not None and not self.visual.isNull: self.visual.update(self.data.getLast(remainder)) #Last update at the end

		if self.param('csv'): self.data.saveCSV(self.param('csv'))
		if self.cpanel:
			self.cpanel.progress.done()
			self.cpanel.runButton.terminate()
		elif self.visual and getattr(self, 'root', False): self.root.destroy() #Quit if we're in cpanel-less mode

		#Re-enable parameters
		for param in self.params.values():
			if param.type=='checkentry' and param.event: continue
			if not param.runtime: param.enable()

		self.doHooks('terminate', [self, self.data.dataframe])

	#param is a string (for a global param), a name,object,item,primitive tuple (for per-breed or per-good params), or a list of such
	def paramSweep(self, param, reporters=None):
		if not self.param('stopafter'): raise RuntimeError(_('Can\'t do a parameter sweep without the value of the \'stopafter\' parameter set.'))

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
			for p in self.params.values():
				if not getattr(p, 'config', False): p.reset()

			for k,v in run.items(): params[k][1].set(v, params[k][0][2] if params[k][1].obj is not None else None)
			self.setup()
			self.start()

			if reporters is not None: data = pandas.DataFrame({k:self.data.all[k] for k in reporters})
			else: data = self.data.dataframe

			events = [Item(name=e.name, triggered=e.triggered, data=e.data) for e in self.events.values()]

			alldata.append(Item(vars=run, data=data, events=events))
		return alldata

	#Creates an unweighted and undirected network of a certain density
	def createNetwork(self, density, kind='edge', prim=None):
		if density < 0 or density > 1: raise ValueError(_('Network density must take a value between 0 and 1.'))
		from itertools import combinations
		agents = self.allagents.values() if prim is None else self.agents[prim]
		for c in combinations(agents, 2):
			if random.randint(0,100) < density*100:
				c[0].newEdge(c[1], kind)
		return self.network(kind, prim)

	def network(self, kind='edge', prim=None, excludePatches=False):
		import networkx as nx

		#Have to use DiGraph in order to draw any arrows
		G = nx.DiGraph(name=kind)
		agents = list(self.allagents.values()) if prim is None else self.agents[prim]
		if excludePatches: agents = [a for a in agents if a.primitive!='patch']
		G.add_nodes_from([(a.id, {'breed': a.breed, 'primitive': a.primitive, 'position': None if a.position is None else a.position.copy()}) for a in agents])
		ae = self.allEdges
		if kind in ae:
			for e in ae[kind]:
				if prim is None or (e.vertices[0].primitive==prim and e.vertices[1].primitive==prim): G.add_edge(
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
		for l in self.agents.values():
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
			ids = [a.id for a in self.allagents.values()]
			maxid = max(ids) if ids else 0 #Figure out maximum existing ID
			for aId in range(maxid+1, maxid+int(diff)+1):
				breed = self.doHooks([prim+'DecideBreed', 'decideBreed'], [aId, self.primitives[prim].breeds.keys(), self])
				if breed is None: breed = list(self.primitives[prim].breeds.keys())[aId%len(self.primitives[prim].breeds)]
				if not breed in self.primitives[prim].breeds:
					raise ValueError(_('Breed \'{0}\' is not registered for the \'{1}\' primitive.').format(breed, prim))
				new = self.primitives[prim].class_(breed, aId, self)
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
				env = globals().copy()
				env['self'] = self
				shell = code.InteractiveConsole(env)
				shell.interact()
			except: print(_('Use pip to install readline and code for a debug console.'))

	#Return agents of a breed if string; return specific agent with ID otherwise
	def agent(self, var, primitive=None):
		if primitive is None:
			primitive = 'agent' if 'agent' in self.primitives else next(iter(self.primitives))
		if isinstance(var, str):
			return [a for a in self.agents[primitive] if a.breed==var]
		else:
			aa = self.allagents
			return aa[var] if var in aa else None

		return None #If nobody matched

	#Returns summary statistics on an agent variable at a single point in time
	def summary(self, var, prim=None, breed=None, good=False):
		if prim is None:
			prim = 'agent' if 'agent' in self.primitives else next(iter(self.primitives))
		agents = self.agents[prim] if breed is None else self.agent(breed, prim)
		if not good: data = pandas.Series([getattr(a, var) for a in agents]) #Pandas gives us nice statistical functions
		else: data = pandas.Series([a.stocks[var] for a in agents])
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
		if hasattr(self, 'breed'): warnings.warn(_('Control panel can only be launched on the top-level model.'), None, 2)

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

		if not isNotebook():
			from helipad.cpanelTkinter import Cpanel
			self.cpanel = Cpanel(self)
			self.doHooks('CpanelPostInit', [self.cpanel]) #Want the cpanel property to be available here, so don't put in cpanel.py
			self.debugConsole()
			self.cpanel.mainloop()		#Launch the control panel
		else:
			from helipad.cpanelJupyter import Cpanel, SilentExit
			if self.cpanel: self.cpanel.invalidate(_('Control panel was redrawn in another cell.'))
			self.cpanel = Cpanel(self)
			self.doHooks('CpanelPostInit', [self.cpanel])
			raise SilentExit() #Don't blow past the cpanel if doing "run all"

		self.doHooks('GUIClose', [self]) #This only executes after all GUI elements have closed

	def launchVisual(self):
		if self.visual is None or self.visual.isNull:
			if not self.cpanel:
				print(_('No visualizations available. To run the model with no GUI, use model.start() instead.'))
				return
			if not self.param('stopafter') or not (self.param('csv') or 'terminate' in self.hooks):
				print(_('Running from the control panel with no visualization requires a stop condition, and either CSV export or a terminate hook.'))
				return

		self.setup()

		if self.visual is not None and not self.visual.isNull:
			self.visual.launch(_('{}Data Plots').format(self.name+(' ' if self.name!='' else '')))
		else: #Headless
			self.params['stopafter'].disable()
			self.params['csv'].disable()

		self.doHooks('visualLaunch', [self, self.visual])

		#If we're running in cpanel-less mode, hook through a Tkinter loop so it doesn't exit on pause
		if not self.cpanel and not self.visual.isNull and not isNotebook():
			from tkinter import Tk
			self.root = Tk()
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

	#===================
	# DEPRECATED METHODS
	#===================

	# DEPRECATED IN HELIPAD 1.4; REMOVE IN HELIPAD 1.6

	def addEvent(self, name, fn, **kwargs):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.addEvent()', 'model.events.add()'), FutureWarning, 2)
		return self.events.add(name, fn, **kwargs)

	def removeEvent(self, name):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.removeEvent()', 'model.events.remove()'), FutureWarning, 2)
		return self.events.remove(name)

	def clearEvents(self):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.clearEvents()', 'model.events.clear()'), FutureWarning, 2)
		self.events.clear()

	def addParameter(self, *args, **kwargs):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.addParameter()', 'model.params.add()'), FutureWarning, 2)
		return self.params.add(*args, **kwargs)

	def addBreedParam(self, name, title, type, dflt, opts={}, prim=None, runtime=True, callback=None, desc=None, getter=None, setter=None):
		if prim is None:
			if len(self.primitives) == 1: prim = next(iter(self.primitives.keys()))
			else: raise KeyError(_('Breed parameter must specify which primitive it belongs to.'))
		return self.addParameter(name, title, type, dflt, opts, runtime, callback, 'breed', desc, prim=prim, getter=getter, setter=setter)

	def addGoodParam(self, name, title, type, dflt, opts={}, runtime=True, callback=None, desc=None, getter=None, setter=None):
		return self.addParameter(name, title, type, dflt, opts, runtime, callback, 'good', desc, getter=getter, setter=setter)

	@property
	def goodParams(self):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.goodParams', 'model.params.perGood'), FutureWarning, 2)
		return self.params.perGood

	@property
	def allParams(self):
		warnings.warn(_('Model.allParams is deprecated. All parameters can be accessed using model.params.'), FutureWarning, 2)
		return self.params.values()

	def addHook(self, place, func, prioritize=False):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.addHook()', 'model.hooks.add()'), FutureWarning, 2)
		return self.hooks.add(place, func, prioritize)

	def removeHook(self, place, fname, removeall=False):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.removeHook()', 'model.hooks.remove()'), FutureWarning, 2)
		return self.hooks.remove(place, fname, removeall=False)

	def clearHooks(self, place):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.clearHooks()', 'model.hooks.clear()'), FutureWarning, 2)
		return self.hooks.remove(place)

	def addPrimitive(self, *args, **kwargs):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.addPrimitive()', 'model.primitives.add()'), FutureWarning, 2)
		return self.primitives.add(*args, **kwargs)

	def removePrimitive(self, name):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.removePrimitive()', 'model.primitives.remove()'), FutureWarning, 2)
		return self.primitives.remove(name)

	def addGood(self, *args, **kwargs):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.addGood()', 'model.goods.add()'), FutureWarning, 2)
		return self.goods.add(*args, **kwargs)

	@property
	def moneyGood(self):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.moneyGood', 'model.goods.money'), FutureWarning, 2)
		return self.goods.money

	@property
	def nonMoneyGoods(self):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('Model.nonMoneyGoods()', 'model.goods.nonmonetary'), FutureWarning, 2)
		return self.goods.nonmonetary

class MultiLevel(baseAgent, Helipad):
	def __init__(self, breed, id, parentModel):
		super().__init__(breed, id, parentModel)
		self.setup()

	#Deprecated in Helipad 1.4; remove in Helipad 1.6
	@property
	def dontStepAgents(self):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('MultiLevel.dontStepAgents', 'MultiLevel.cutStep()'), FutureWarning, 2)
		return self._cut

	@dontStepAgents.setter
	def dontStepAgents(self, val):
		warnings.warn(_('{0} is deprecated and has been replaced with {1}.').format('MultiLevel.dontStepAgents', 'MultiLevel.cutStep()'), FutureWarning, 2)
		self._cut = val

#==================
# CONTAINER CLASSES
#==================

#For adding breeds and goods. Should not be called directly
class gandb(funcStore):
	def __init__(self, model):
		self.model = model

	def add(self, obj, name, color, prim=None, **kwargs):
		if name in self:
			warnings.warn(_('{0} \'{1}\' already defined. Overriding…').format(obj, name), None, 2)

		cobj = color if isinstance(color, Color) else Color(color)
		cobj2 = cobj.lighten()
		self[name] = Item(color=cobj, color2=cobj2, **kwargs)

		#Make sure the parameter lists keep up with our items
		if obj=='good': paramDict = self.model.params.perGood
		elif obj=='breed': paramDict = {k:v for k,v in self.model.params.perBreed.items() if v.prim==self.primitive}
		for p in paramDict.values(): p.addKey(name)

		return self[name]

	def remove(self, name):
		if isinstance(name, (list, tuple)): return [self.remove(n) for n in name]
		if not name in self: return False

		#Also delete per-item parameters
		pdict = self.model.params.perBreed if isinstance(self, Breeds) else self.model.params.perGood
		for param in pdict.values():
			del param.value[name]
			if getattr(param, 'elements', False):
				if not isNotebook(): param.elements[name].destroy()
				else: param.elements[name].close()
				del param.elements[name]
		return super().remove(name)

class Goods(gandb):
	def add(self, name, color, endowment=None, money=False, props={}):
		if money:
			if self.money is not None:
				print(_('Money good already specified as {}. Overriding…').format(self.money))
				self[self.money].money = False

			#Add the M0 plot once we have a money good, only if we haven't done it before
			elif (self.model.visual is None or self.model.visual.isNull) and hasattr(self.model.visual, 'plots'):
				try:
					if not 'money' in self.model.visual.plots: self.model.visual.addPlot('money', _('Money'), selected=False)
				except: pass #Can't add plot if re-drawing the cpanel

		props['quantity'] = endowment
		item = super().add('good', name, color, money=money, props=props)

		#Add demand plot once we have at least 2 goods
		if len(self) == 2 and (self.model.visual is None or self.model.visual.isNull) and hasattr(self.model.visual, 'plots'):
			try:
				if not 'demand' in self.model.visual.plots: self.model.visual.addPlot('demand', _('Demand'), selected=False)
			except: pass

		return item

	@property
	def money(self):
		for name,good in self.items():
			if good.money: return name
		return None

	@property
	def nonmonetary(self):
		return {k:v for k,v in self.items() if not v.money}

class Breeds(gandb):
	def __init__(self, model, primitive):
		self.primitive = primitive
		super().__init__(model)

	def add(self, name, color): return super().add('breed', name, color)

class Primitives(funcStore):
	def __init__(self, model):
		self.model = model
		super().__init__()

	def add(self, name, class_, plural=None, dflt=50, low=1, high=100, step=1, hidden=False, priority=100, order=None):
		if name=='all': raise ValueError(_('{} is a reserved name. Please choose another.').format(name))
		if not plural: plural = name+'s'
		class_.primitive = name
		self[name] = Item(
			class_=class_,
			plural=plural,
			priority=priority,
			order=order,
			breeds=Breeds(self.model, name)
		)
		def popget(name, model):
			prim = name.split('_')[1]
			if not model.hasModel: return None
			else: return len(model.agents[prim])

		self.model.params.add('num_'+name, 'Number of '+plural.title(), 'hidden' if hidden else 'slider', dflt=dflt, opts={'low': low, 'high': high, 'step': step} if not hidden else None, setter=self.model.nUpdater, getter=popget)
		self.model.agents[name] = []

	def remove(self, name):
		val = super().remove(name)
		if val:
			del self.model.agents[name]
			del self.model.params['num_'+name]
		return val

class Events(funcStore):
	def __init__(self):
		super().__init__()
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
		self.Event = Event

	def add(self, name, fn, **kwargs):
		return super().add(name, self.Event(name, fn, **kwargs))

class Hooks(funcStore):
	multi = True

	def add(self, name, function, prioritize=False):
		deprec = {
			'networkNodeClick': 'agentClick',	#1.3; can be removed in 1.5
			'spatialAgentClick': 'agentClick',	#1.3; can be removed in 1.5
			'spatialPatchClick': 'patchClick'	#1.3; can be removed in 1.5
		}
		if name in deprec:
			warnings.warn(_('The {0} hook is deprecated and has been replaced with {1}.').format(name, deprec[name]), FutureWarning, 2)
			name = deprec[name]

		if not name in self: self[name] = []
		if prioritize: self[name].insert(0, function)
		else: self[name].append(function)