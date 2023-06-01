"""
The main model module. Import and instantiate the `Helipad` class to set up and launch a model. See https://helipad.dev for API documentation.
"""

import os, sys, warnings, asyncio, time
import gettext
from random import shuffle, choice
#from memory_profiler import profile

from helipad.visualize import BaseVisualization, Charts, TimeSeries
from helipad.helpers import *
from helipad.param import Params, Shocks
from helipad.data import Data
from helipad.agent import *

class Helipad:
	"""The main model object. https://helipad.dev/functions/model/"""
	runInit = True #for multiple inheritance. Has to be a static property

	def __init__(self, locale: str='en'):
		#Have to do this first so that i18n is available early.
		#Put it in an obscure variable and then use helpers.ï() so we don't conflict with the REPL console, which overwrites _.
		if not hasattr(self, 'breed'):
			import builtins
			builtins.__dict__['helipad_gettext'] = gettext.translation('helipad', localedir=os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))+'/locales', languages=[locale]).gettext

		#Containers
		self.agents = Agents(self)
		self.data = Data(self)
		self.params = Params(self)
		self.shocks = Shocks(self)
		self.events = Events()
		self.hooks = Hooks()
		self.goods = Goods(self)

		self.name = ''
		self.patches = []
		self.stages = 1
		self.hasModel = False		#Have we initialized?
		self.timer = False
		self.visual = None
		self.cpanel = None

		self.t = None
		self.running = False
		self._cut = False

		#Default parameters
		self.agents.addPrimitive('agent', Agent, dflt=50, low=1, high=100)

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
			self.params.add('stopafter', ï('Stop on period'), 'checkentry', False, runtime=True, config=True, entryType='int', callback=switchPbar)
			self.params.add('csv', ï('CSV?'), 'checkentry', False, runtime=True, config=True)
			self.params.add('refresh', ï('Refresh Every __ Periods'), 'slider', 20, opts=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], runtime=True, config=True)
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
					print(ï('A Helipad update is available! Use `pip install -U helipad` to upgrade to version {}.').format(available[0]))
			except: pass #Fail silently if we're not online

	def __repr__(self):
		if self.name: return f'<Helipad: {self.name}>'
		else: return '<Helipad object>'

	def addButton(self, text: str, func, desc=None):
		"""Add a button to the control panel, in the shocks section, that runs `func` when pressed. This method is aliased by the `@model.button` function decorator, which is preferred. https://helipad.dev/functions/model/addbutton/"""
		self.shocks.add(text, None, func, 'button', True, desc)

	def param(self, param, val=None):
		"""Get or set a model parameter, depending on whether there are two or three arguments. https://helipad.dev/functions/model/param/"""
		item = param[2] if isinstance(param, tuple) and len(param)>2 else None
		param = self.params[param[0]] if isinstance(param, tuple) else self.params[param]

		if val is not None: param.set(val, item)
		else: return param.get(item)

	def doHooks(self, place: str, args: list):
		"""Execute registered hooks at various places in the model and return the value of the last function in the list. https://helipad.dev/functions/model/dohooks/"""
		#Take a list of hooks; go until we get a response
		if isinstance(place, list):
			for f in place:
				r = self.doHooks(f, args)
				if r is not None: return r
			return None

		if not place in self.hooks: return None
		for f in self.hooks[place]: r = f(*args)
		return r

	def useVisual(self, viz: BaseVisualization):
		"""Register a visualization class for live model visualization. Visualization classes can be imported from `helipad.visualize`, or custom visualization classes can be subclassed from `BaseVisualization`. The visualization can then be launched later using model.launchVisual(). https://helipad.dev/functions/model/usevisual/"""
		if hasattr(self, 'breed'):
			warnings.warn(ï('Visualizations can only be registered on the top-level model.'), None, 2)
			return #Doesn't matter if it's not the top-level model

		if viz is not None and not issubclass(viz, BaseVisualization):
			raise RuntimeError(ï('Visualization class must inherit from BaseVisualization.'))

		self.visual = viz(self) if viz is not None else None
		return self.visual

	def setup(self):
		"""Gather the control panel settings and initialize the model. This function runs when the "New Model" button is pressed, and should not be called by user code. https://helipad.dev/functions/model/setup/"""
		if self.hasModel: self.terminate()
		self.doHooks('modelPreSetup', [self])
		self.t = 0

		#Blank breeds for any primitives not otherwise specified
		for p in self.agents.values():
			if not p.breeds: p.breeds.add('', '#000000')

		#SERIES AND REPORTERS
		#Breeds and goods should already be registered at this point

		self.data.reset()
		for e in self.events.values(): e.reset()
		defPrim = 'agent' if 'agent' in self.agents else next(iter(self.agents))

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
			if self.visual is not None and isinstance(self.visual, TimeSeries) and 'money' in self.visual:
				self.visual['money'].addSeries('M0', ï('Monetary Base'), self.goods[self.goods.money].color)

		#Unconditional variables to report
		# self.data.addReporter('utility', self.data.agentReporter('utils', defPrim))

		#Per-breed and per-good series and reporters
		#Don't put lambda functions in here, or the variable pairs will be reported the same, for some reason.
		for breed, b in self.agents[defPrim].breeds.items():
			self.data.addReporter('utility-'+breed, self.data.agentReporter('utils', defPrim, breed=breed))
			if self.visual is not None and self.visual.__class__.__name__=='TimeSeries':
				self.visual['utility'].addSeries('utility-'+breed, breed.title()+' '+ï('Utility'), b.color)

		if len(self.goods) >= 2:
			for good, g in self.goods.nonmonetary.items():
				self.data.addReporter('demand-'+good, self.data.agentReporter('currentDemand', 'all', good=good, stat='sum'))
				if self.visual is not None:
					if 'demand' in self.visual: self.visual['demand'].addSeries('demand-'+good, good.title()+' '+ï('Demand'), g.color)

		#Initialize agents
		for prim, ags in self.agents.items():
			ags.clear()																	#Clear any surviving agents from last run
			self.agents.initialize(self.param('num_'+prim), prim, self, force=True)		#Force is so we can call initialize() before instantiating hasModel

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
				raise ImportError(ï('nest_asyncio is required to run Helipad from Spyder.'))

		self.hasModel = True
		self.doHooks('modelPostSetup', [self])

	def cutStep(self):
		"""When called from inside an `agentStep` or `match` hook, skip stepping the rest of the agents that stage and proceed to the next (or to the next period in single-stage models). https://helipad.dev/functions/model/cutstep/"""
		self._cut = True

	def step(self, stage: int=1):
		"""Step the model, i.e. run through the `step()` functions of all the agents and increment the timer by one. This method is called automatically while the model is running, and should not generally be called in user code. https://helipad.dev/functions/model/step/"""
		self.t += 1
		self.doHooks('modelPreStep', [self])

		#Reset per-period variables
		#Have to do this all at once at the beginning of the period, not when each agent steps
		for p in self.agents.values():
			for a in p: a.currentDemand = {g:0 for g in self.goods}

		self.shocks.step()

		def sortFunc(model: Helipad, stage: int, func):
			def sf(agent): return func(agent, model, stage)
			return sf

		for self.stage in range(1, self.stages+1):
			self._cut = False
			self.doHooks('modelStep', [self, self.stage])

			#Sort agents and step them
			for prim, lst in self.agents.items():
				order = lst.order or self.agents.order
				if isinstance(order, list): order = order[self.stage-1]
				if order == 'random': shuffle(lst)

				#Can't do our regular doHooks() here since we want to pass the function to .sort()
				#From the user's perspective though, this doesn't matter
				#Do the more specific sorts last
				ordhooks = (self.hooks['order'] if 'order' in self.hooks else []) + (self.hooks[prim+'Order'] if prim+'Order' in self.hooks else [])
				for o in ordhooks: lst.sort(key=sortFunc(self, self.stage, o))

				#Copy the agent list to keep it constant for a given loop because modifying it
				#while looping (e.g. if an agent dies or reproduces) will screw up the looping
				agentpool = list(lst)

				#Matching model
				if 'match' in order:
					matchN = int(mn[1]) if len(mn := order.split('-')) > 1 else 2
					matchpool = list(lst)
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
									else: raise ValueError(ï('matchSelect did not return the correct number of agents.'))

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

				#Update visualizations
				if self.visual is not None and not self.visual.isNull:
					await asyncio.sleep(0.001) #Listen for keyboard input
					data = self.data.getLast(t - self.visual.lastUpdate)

					self.visual.refresh(data)
					self.visual.lastUpdate = t

					self.doHooks('visualRefresh', [self, self.visual])

				elif self.cpanel:
					if isNotebook(): await asyncio.sleep(0.001) #Listen for keyboard input
					else: self.cpanel.update() #Make sure we don't hang the interface if plotless

				# Performance indicator
				if self.timer:
					newtime = time.time()
					output = ï('Period {0}: {1} periods/second ({2}% model, {3}% visuals)').format(t, round(self.param('refresh')/(newtime-begin),2), round((t2-begin)/(newtime-begin)*100,2), round((newtime-t2)/(newtime-begin)*100,2))
					if isBuffered():
						if isNotebook(): os.write(1, bytes('\r'+output, 'utf-8'))
						else: sys.stdout.write('\r'+output)
					else: print(output)
					begin = newtime

			if st:
				stop = self.events[st].triggered if isinstance(st, str) else t>=st
				if stop: self.terminate()
		if self.timer and isBuffered(): print('\r') #Newline on pause so the output doesn't interfere with the console

	#The *args allows it to be used as an Ipywidgets callback
	#@profile #To test memory usage
	def start(self, *args):
		"""Start a model, running `model.setup()` if `model.hasModel` is `False`, and otherwise resuming the existing model. This function is called by `model.launchVisual()`, but does not call it. Use that function to start the model instead if output plots are desired. https://helipad.dev/functions/model/start/"""
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
		"""Pause the model, allowing it to be subsequently resumed. https://helipad.dev/functions/model/stop/"""
		self.running = False
		if self.cpanel:
			self.cpanel.progress.stop()
			self.cpanel.runButton.pause()
		self.doHooks('modelStop', [self])

	def terminate(self, evt=False):
		"""Terminate the running model and write the data to disk, if applicable. https://helipad.dev/functions/model/terminate/"""
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

		#Re-enable parameters
		for param in self.params.values():
			if param.type=='checkentry' and param.event: continue
			if not param.runtime: param.enable()

		self.doHooks('terminate', [self, self.data.dataframe])

	#param is a string (for a global param), a name,object,item,primitive tuple (for per-breed or per-good params), or a list of such
	def paramSweep(self, param, reporters=None):
		"""Repeatedly run the model while systematically varying one or more parameter values. Possible values to be swept are specified when the parameter is registered. https://helipad.dev/functions/model/paramsweep/"""
		if not self.param('stopafter'): raise RuntimeError(ï('Can\'t do a parameter sweep without the value of the \'stopafter\' parameter set.'))

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

	def spatial(self, *args, **kwargs):
		from helipad.spatial import spatialSetup
		return spatialSetup(self, *args, **kwargs)

	# Only works on Mac. Also Gnureadline borks everything, so don't install that.
	# Has to be called *after* Cpanel.__init__() is called, or the cpanel object won't be available.
	def debugConsole(self):
		"""Launch a REPL console to interact with the model after launch. Requires to be run in a buffered console. `self` will refer to the model object."""
		if sys.platform=='darwin' and isBuffered():
			try:
				import code, readline # Readline doesn't look like it's doing anything here, but it enables certain console features
				env = globals().copy()
				env['self'] = self
				code.interact(local=env)
			except ModuleNotFoundError: print(ï('Error initializing the debug console. Make sure the `readline` and `code` modules are installed.'))

	def launchCpanel(self, console: bool=True):
		"""Launch the control panel, either in a Tkinter or a Jupyter environment, as appropriate. https://helipad.dev/functions/model/launchcpanel/"""
		if hasattr(self, 'breed'): warnings.warn(ï('Control panel can only be launched on the top-level model.'), None, 2)

		self.doHooks('CpanelPreLaunch', [self])

		#Set our agents slider to be a multiple of how many agent types there are
		#Do this down here so we can have breeds registered before determining options
		for k,p in self.agents.items():
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
			if console: self.debugConsole()
			self.cpanel.mainloop()		#Launch the control panel
		else:
			from helipad.cpanelJupyter import Cpanel, SilentExit
			if self.cpanel: self.cpanel.invalidate(ï('Control panel was redrawn in another cell.'))
			self.cpanel = Cpanel(self)
			self.doHooks('CpanelPostInit', [self.cpanel])
			raise SilentExit() #Don't blow past the cpanel if doing "run all"

		self.doHooks('GUIClose', [self]) #This only executes after all GUI elements have closed

	def launchVisual(self):
		"""Launch the visualization window from the class registered in `model.useVisual()`, and start the model. https://helipad.dev/functions/model/launchvisual/"""
		if self.visual is None or self.visual.isNull:
			if not self.cpanel:
				print(ï('No visualizations available. To run the model with no GUI, use model.start() instead.'))
				return
			if not self.param('stopafter') or not (self.param('csv') or 'terminate' in self.hooks):
				print(ï('Running from the control panel with no visualization requires a stop condition, and either CSV export or a terminate hook.'))
				return

		self.setup()

		if self.visual is not None and not self.visual.isNull:
			self.visual.launch(ï('{}Data Plots').format(self.name+(' ' if self.name!='' else '')))
		else: #Headless
			self.params['stopafter'].disable()
			self.params['csv'].disable()

		self.doHooks('visualLaunch', [self, self.visual])

		#If we're running in cpanel-less mode, hook through a Tcl loop so it doesn't exit on pause
		if not self.cpanel and not self.visual.isNull and not isNotebook():
			from tkinter import Tcl
			root = Tcl()
			root.after(1, self.start)
			self.debugConsole()
			root.mainloop()
		else: self.start() #As long as we haven't already started

	# Generates function decorators for hooks, reporters, etc.
	def genDecorator(self, todo):
		"""Return a function which can either serve as a decorator itself or return another decorator function, for use in various decorators (`@model.hook`, `@model.reporter`, and `@model.button`). https://helipad.dev/functions/model/gendecorator/"""
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

	#
	#Deprecated in 1.6, remove in 1.8
	#

	@property
	def allagents(self):
		"""A list of all agents. This property is deprecated; use `model.agents.all` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.allagents', 'model.agents.all'), FutureWarning, 2)
		return self.agents.all

	@property
	def primitives(self):
		"""A list of primitive data. This property is deprecated; use `model.agents` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.primitives', 'model.agents'), FutureWarning, 2)
		return self.agents

	@property
	def order(self):
		"""The order in which to step agents. This property is deprecated; use `model.agents.order` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.order', 'model.agents.order'), FutureWarning, 2)
		return self.agents.order
	@order.setter
	def order(self, val):
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.order', 'model.agents.order'), FutureWarning, 2)
		self.agents.order = val

	def addBreed(self, name, color, prim=None):
		"""Add a breed to a given primitive. This method is deprecated; use `model.agents.addBreed()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.addBreed', 'model.agents.addBreed'), FutureWarning, 2)
		return self.agents.addBreed(name, color, prim)

	def createNetwork(self, density, kind='edge', prim=None):
		"""Create a network of a given density among agents. This method is deprecated; use `model.agents.createNetwork()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.createNetwork', 'model.agents.createNetwork'), FutureWarning, 2)
		return self.agents.createNetwork(density, kind, prim)

	def network(self, kind='edge', prim=None, excludePatches=False):
		"""Return the network structure of a set of agents. This method is deprecated; use `model.agents.network()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.network', 'model.agents.network'), FutureWarning, 2)
		return self.agents.network(kind, prim, excludePatches)

	@property
	def allEdges(self):
		"""A `dict` of all network edges between agents, organized by kind. This property is deprecated; use `model.agents.edges` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.allEdges', 'model.agents.edges'), FutureWarning, 2)
		return self.agents.edges._dict

	def agent(self, var, primitive=None):
		"""Retrieve an agent by ID or breed. This method is deprecated; use `model.agents[primitive][breed]` or `model.agents[id]` instead."""
		if isinstance(var, str):
			warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.agent(breed)', 'model.agents[primitive][breed]'), FutureWarning, 2)
			if primitive is None: primitive = next(iter(self.agents))
			return self.agents[primitive][var]
		else:
			warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.agent(id)', 'model.agents[id]'), FutureWarning, 2)
			return self.agents[var]

	def summary(self, var, prim=None, breed=None, good=False):
		"""Print summary statistics on an agent property. This method is deprecated; use `model.agents.summary()` instead."""
		warnings.warn(ï('{0} is deprecated and has been replaced with {1}.').format('model.summary()', 'model.agents.summary()'), FutureWarning, 2)
		return self.agents.summary(var, prim, breed, good)

class MultiLevel(baseAgent, Helipad):
	"""A class allowing multi-level agent-based models to be constructed, where the agents at one level are themselves full models with sub-agents. Inherits from both `baseAgent` and `Helipad`. https://helipad.dev/functions/multilevel/"""
	def __init__(self, breed, id, parentModel):
		super().__init__(breed, id, parentModel)
		self.setup()

#==================
# CONTAINER CLASSES
#==================

class Events(funcStore):
	"""Interface to add and store events that can trigger during a model on a certain user-defined criterion. https://helipad.dev/functions/events/"""
	def __init__(self):
		super().__init__()
		class Event:
			"""An event triggers on a certain user-defined criterion. When triggered, an event stores the data output at that time and registers on the visualizer. This class should not be instantiated directly; use Events.add() or the @model.event decorator instead. https://helipad.dev/functions/event/"""
			def __init__(self, name: str, trigger, repeat: bool=False, **kwargs):
				self.name = name
				self.trigger = trigger
				self.repeat = repeat
				self.kwargs = kwargs
				self.data = []
				self.triggered = []
				self.reset()

			def check(self, model: Helipad) -> bool:
				"""Run the user-defined event function to determine whether the event is triggered, and record the model state if so. If `Event.repeat==False`, return `False` so long as `Event.trigger` returns `False`, `True` the first time `Event.trigger` returns `True`, and `False` thereafter. If `Event.repeat==True`, return `True` whenever `Event.trigger` returns `True`. https://helipad.dev/functions/event/check/"""
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
				"""Clear `Event.data` and set `Event.triggered` to `False`. https://helipad.dev/functions/event/reset/"""
				if self.repeat:
					self.data.clear()
					self.triggered.clear()
				else:
					self.data = None
					self.triggered = False
		self.Event = Event

	def add(self, name: str, function, **kwargs):
		"""Register an Event. When triggered, an event stores the data output at that time and registers on the visualizer. https://helipad.dev/functions/events/add/"""
		return super().add(name, self.Event(name, function, **kwargs))

class Goods(gandb):
	"""Interface to add and store goods that agents can own. Stored in `model.goods`. https://helipad.dev/functions/goods/"""
	def add(self, name: str, color, endowment=None, money: bool=False, props=None):
		"""Register a good that agents can carry or trade. Agents keep track of stocks of the good in `agent.stocks`. Quantities of a good can then be accessed with `agent.stocks[good]`, and properties of the good with a two-argument index, e.g. `agent.stocks[good, 'property']`. https://helipad.dev/functions/goods/add/"""
		if not props: props = {}
		if money:
			if self.money is not None:
				print(ï('Money good already specified as {}. Overriding…').format(self.money))
				self[self.money].money = False

			#Add the M0 plot once we have a money good, only if we haven't done it before
			elif (self.model.visual is None or self.model.visual.isNull) and hasattr(self.model.visual, 'plots'):
				try:
					if not 'money' in self.model.visual: self.model.visual.addPlot('money', ï('Money'), selected=False)
				except: pass #Can't add plot if re-drawing the cpanel

		props['quantity'] = endowment
		item = super().add('good', name, color, money=money, props=props)

		#Add demand plot once we have at least 2 goods
		if len(self) == 2 and (self.model.visual is None or self.model.visual.isNull) and hasattr(self.model.visual, 'plots'):
			try:
				if not 'demand' in self.model.visual: self.model.visual.addPlot('demand', ï('Demand'), selected=False)
			except: pass

		return item

	@property
	def money(self):
		"""The name of the good serving as a numeraire. This property is set by the `money` parameter of `Goods.add()`. https://helipad.dev/functions/goods/#money"""
		for name,good in self.items():
			if good.money: return name
		return None

	@property
	def nonmonetary(self) -> dict:
		"""The subset of goods minus the money good. https://helipad.dev/functions/goods/#nonmonetary"""
		return {k:v for k,v in self.items() if not v.money}

class Hooks(funcStore):
	"""Interface to add and store hooks, allowing user-defined code to be inserted into the model. https://helipad.dev/functions/hooks/"""
	multi: bool = True

	def add(self, name: str, function, prioritize: bool=False):
		"""Inserts a function into designated places in the model’s logic. See the Hooks Reference (https://helipad.dev/glossary/hooks/) for a complete list of possible hooks and the function signatures necessary to use them. This method is aliased by the `@model.hook` function decorator, which is the preferred way to hook functions. https://helipad.dev/functions/hooks/add/"""
		if not name in self: self[name] = []
		if prioritize: self[name].insert(0, function)
		else: self[name].append(function)