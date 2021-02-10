from ipywidgets import interactive, Layout, Accordion, HBox, VBox, HTML, Label, Button, FloatProgress
from IPython.display import display
from helipad.param import Param
import os

class Cpanel(VBox):
	def __init__(self, model, redraw=False):
		super().__init__()
		self.model = model
		if redraw:
			self.children = ()
			self.remove_class('invalid')
		else: self.add_class('helipad_cpanel')
		self.valid = True
		
		#CSS niceties
		__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
		with open(os.path.join(__location__,'ipy-styles.css')) as c: css = c.read()
		self.children += (HTML(value='<style type="text/css">'+css+'</style>'),)
		
		#Callback function generator for Jupyter elements
		def setVar(param, item=None):
			def sv(val): #Ipywidgets bases on the function signature, so can't use more than one here…
				if param.type=='checkgrid': param.set(item, val, updateGUI=False)
				else: param.set(val, item, updateGUI=False)
				
				if callable(param.callback):
					if param.obj is None: param.callback(self.model, param.name, param.get(item))
					else: param.callback(self.model, param.name, item, param.get(item))
			
			#Consolidate value from bool and string, and toggle entry disabled state
			#Have to return a different function since Ipywidgets bases the interactive off the function signature
			if param.type=='checkentry':
				def sv2(b,s):
					els = param.element if item is None else param.element[item]
					els.children[1].disabled = not b
					#Coercing an int can fail, so if there's an exception, reset the textbox content
					try:
						val = s if (b and s=='') or 'func〈' in s else (param.entryType(s) if b else False)
						sv(val)
					except: els.children[1].value = str(param.get())
					
				return sv2
			else: return sv
		Param.setVar = setVar
		
		def renderParam(param, func, title, val, circle=None):
			i=None
			if param.type=='slider':
				if isinstance(param.opts, dict): i = interactive(func, val=(param.opts['low'],param.opts['high'], param.opts['step']))
				else:
					s = interactive(func, val=(0, len(param.opts)-1, 1))
					s.children[0].readout = False
					l = Label(value=str(param.opts[0]), layout=Layout(margin='0 0 0 15px'))
					i = HBox([s.children[0],l])
					
			elif param.type=='check':
				i = interactive(func, val=val)
			elif param.type=='menu':
				i = interactive(func, val=[(k[1], k[0]) for k in param.opts.items()])
			elif param.type=='checkentry':
				defaults = (
					(isinstance(val, param.entryType) or val) if not (param.name=='stopafter' and param.event) else True,				#Bool
					(str(val) if isinstance(val, param.entryType) else '') if not (param.name=='stopafter' and param.event) else 'Event: '+val	#Str
				)
				i = interactive(func, b=defaults[0], s=defaults[1])
				if param.obj is None:
					i = HBox(i.children)
					i.children[0].layout = Layout(width='150px')
				if val==False: i.children[1].disabled = True
				i.children[1].description = ''
				
				if param.name=='stopafter' and param.event:
					i.children[0].disabled = True
					i.children[1].disabled = True
					i.add_class('helipad_checkentry_func')
			elif param.type=='checkgrid':
				param.element = {}
				for k,v in param.opts.items():
					if not isinstance(v, (tuple, list)): v = (v, None)
					elif len(v) < 2: v = (v[0], None)
					param.element[k] = interactive(param.setVar(k), val=param.vars[k])
					param.element[k].children[0].description = v[0]
					param.element[k].children[0].description_tooltip = v[1] if v[1] is not None else '' #Not working, not sure why
				param.containerElement = HBox(list(param.element.values()))
				i = Accordion(children=[param.containerElement])
				i.set_title(0, title)
				i.add_class('helipad_checkgrid')
	
			if i is not None and param.type!='checkgrid':
				circle='<span class="helipad_circle" style="background:'+circle.hex+'"></span>' if circle is not None else ''
				i.children[0].description = circle+title
				i.children[0].style = {'description_width': 'initial'} #Don't truncate the label
				i.children[0].description_tooltip = param.desc if param.desc is not None else ''
				if param.type=='slider' and isinstance(param.opts, list):
					i.children[1].value = str(val)
					if val in param.opts: val=param.opts.index(val)
				if param.type!='checkentry': i.children[0].value = val
	
			return i
		
		def constructAccordion(param, itemList):
			param.element = {}
			for item, good in itemList.items():
				param.element[item] = renderParam(param, param.setVar(item), item.title(), param.get(item), circle=good.color)
		
			accordion = Accordion(children=[HBox(list(param.element.values()))])
			accordion.set_title(0, param.title)
			accordion.add_class('helipad_param_peritem')
			return accordion
		
		ctop = self.model.doHooks('CpanelTop', [self, None])
		if ctop: self.children += (ctop,)
	
		#Global config
		for n,param in model.params.items():
			if not getattr(param, 'config', False) or param.type=='checkgrid': continue
			param.element = renderParam(param, param.setVar(), param.title, param.get())
			if param.element is not None: self.children += (param.element,)
			if param.name=='csv': param.set('filename')
			if n=='stopafter' and not param.event: param.element.children[1].value = '10000'
			if param.type=='checkentry' and getattr(param, 'config', False) and not (n=='stopafter' and param.event): param.set(False)
		
		caip = self.model.doHooks('CpanelAboveItemParams', [self, None])
		if caip: self.children += (caip,)
		
		#Per-good parameters
		for param in model.goodParams.values():
			self.children += (constructAccordion(param, model.nonMoneyGoods),)
	
		#Per-breed parameters
		for prim in model.primitives.values():
			for param in prim.breedParams.values():
				self.children += (constructAccordion(param, prim.breeds),)
		
		cap = self.model.doHooks('CpanelAboveParams', [self, None])
		if cap: self.children += (cap,)
	
		#Global parameters
		for param in model.params.values():
			if getattr(param, 'config', False) or param.type=='checkgrid': continue
			param.element = renderParam(param, param.setVar(), param.title, param.get())
			if param.element is not None: self.children += (param.element,)
		
		#Checkgrids
		for param in model.params.values():
			if param.type!='checkgrid' or param.name=='shocks': continue
			acc = renderParam(param, None, param.title, None)
			if acc is not None: self.children += (acc,)
		
		cas = self.model.doHooks('CpanelAboveShocks', [self, None])
		if cas: self.children += (cas,)
		
		#Shocks
		if len(model.shocks.shocks):
			def sfuncButton(slef, *args): slef.do(self.model)
			model.shocks.Shock.setButton = sfuncButton
			model.params['shocks'].element = {}
			children = []
			for shock in model.shocks.shocksExceptButtons.values():
				shock.element = interactive(shock.setCallback, val=shock.selected)
				shock.element.children[0].description = shock.name
				shock.element.children[0].description_tooltip = shock.desc if shock.desc is not None else ''
				children.append(shock.element)
				model.params['shocks'].element[shock.name] = shock.element #For setting via model.param()
			buttons = []
			for shock in model.shocks.buttons.values():
				shock.element = Button(description=shock.name, icon='bolt')
				shock.element.click = shock.setButton
				shock.element.description_tooltip = shock.desc if shock.desc is not None else ''
				buttons.append(shock.element)
			children.append(HBox(buttons))
			sacc = Accordion(children=[VBox(children)])
			sacc.set_title(0, 'Shocks')
			self.children += (sacc,)
		
		cbot = self.model.doHooks('CpanelBottom', [self, None])
		if cbot: self.children += (cbot,)
		
		self.postinstruct = self.displayAlert('After setting parameter values, run launchVisual() or start() to start the model.')
		if not redraw:
			display(self)
		
			class progressBar(FloatProgress):
				def __init__(self):
					super().__init__(min=0, max=1)
			
				def determinate(self, det):
					self.mode = 'determinate' if det else 'indeterminate'
					if det: self.remove_class('indeterminate')
					else:
						self.add_class('indeterminate')
						self.value = 1
			
				def update(self, n): self.value = n
				def start(self): self.add_class('helipad_running')
				def stop(self): self.remove_class('helipad_running')
				def done(self): self.layout.visibility = 'hidden'
		
			class runButton(Button):
				def __init__(self2, **kwargs):
					super().__init__(**kwargs)
					self2.click = self.model.stop
						
				def run(self2):
					self2.click = self.model.stop
					self2.description = 'Pause'
					self2.icon = 'pause'
			
				def pause(self2):
					self2.click = self.model.start
					self2.description = 'Run'
					self2.icon = 'play'
			
				def terminate(self):
					self.layout.visibility = 'hidden'
			
			#Remove previous hooks so we don't double up when re-running launchCpanel()
			model.removeHook('modelPreSetup', 'cpanel_visualPreLaunch')
			model.removeHook('terminate', 'cpanel_terminate')
		
			#Model flow control: pause/run button and progress bar
			@model.hook('modelPreSetup', prioritize=True)
			def cpanel_visualPreLaunch(model):
				self.runButton = runButton(description='Pause', icon='pause')
				self.progress = progressBar()
				self.postinstruct.layout = Layout(display='none')
				
				self.stopbutton = Button(description='Stop', icon='stop')
				self.stopbutton.click = self.model.terminate
				
				pbararea = HBox([self.runButton, self.stopbutton, self.progress])
				pbararea.add_class('helipad_progress_area')
				display(pbararea)
		
			@model.hook('terminate')
			def cpanel_terminate(model, data):
				self.postinstruct.layout = Layout(display='inline-block')
				self.stopbutton.layout.visibility = 'hidden'

	def displayAlert(self, text, inCpanel=True):
		element = Label(value=text)
		element.add_class('helipad_info')
		if inCpanel: self.children += (element,)
		else: display(element)
		return element
	
	def invalidate(self, message='Model parameters changed, please re-launch the control panel with launchCpanel().'):
		self.valid = False
		self.add_class('invalid')
		warning = Label(value=message)
		warning.add_class('helipad_modal')
		self.children += (warning,)
		for p in self.model.allParams: del p.element
		return warning

#https://stackoverflow.com/questions/24005221/ipython-notebook-early-exit-from-cell
class SilentExit(Exception):
	def _render_traceback_(self): pass