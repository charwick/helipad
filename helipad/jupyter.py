from ipywidgets import interactive, Layout, Accordion, HBox, VBox, HTML, Label, Button
from IPython.display import display
from helipad.graph import Plot
import os

class JupyterCpanel:
	def __init__(self, model):
		self.model = model
		
		#CSS niceties
		__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
		with open(__location__+'/ipy-styles.css') as c: css = c.read() 
		display(HTML(value='<style type="text/css">'+css+'</style>'))
		
		def renderParam(param, func, title, val, circle=None):
			i=None
			if param.type=='slider':
				if isinstance(param.opts, dict): i = interactive(func, val=(param.opts['low'],param.opts['high'], param.opts['step']))
				else:
					s = interactive(func, val=(0, len(param.opts)-1,  1))
					s.children[0].readout = False
					l = Label(value=str(param.opts[0]), layout=Layout(margin='0 0 0 15px'))
					i = HBox([s.children[0],l])
					
			elif param.type=='check':
				i = interactive(func, val=val)
			elif param.type=='menu':
				i = interactive(func, val=[(k[1], k[0]) for k in param.opts.items()])
			elif param.type=='checkentry':
				defaults = (
					(isinstance(val, param.entryType) or val) if not callable(val) else True,				#Bool
					(str(val) if isinstance(val, param.entryType) else '') if not callable(val) else 'func〈'+param.func.__name__+'〉'	#Str
				)
				i = interactive(func, b=defaults[0], s=defaults[1])
				if param.obj is None:
					i = HBox(i.children)
					i.children[0].layout = Layout(width='150px')
				if val==False: i.children[1].disabled = True
				i.children[1].description = ''
				
				if getattr(param, 'func', None) is not None:
					i.children[0].disabled = True
					i.children[1].disabled = True
					i.add_class('helipad_checkentry_func')
			elif param.type=='checkgrid':
				param.element = {}
				for k,v in param.opts.items():
					param.element[k] = interactive(param.setf(k), val=param.vars[k])
					param.element[k].children[0].description = v[0]
					param.element[k].children[0].description_tooltip = v[1] if v[1] is not None else '' #Not working, not sure why
				i = Accordion(children=[HBox(list(param.element.values()))])
				i.set_title(0, title)
				i.add_class('helipad_checkgrid')
	
			if i is not None and param.type!='checkgrid':
				circle='<span class="helipad_circle" style="background:'+circle.hex_l+'"></span>' if circle is not None else ''
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
				param.element[item] = renderParam(param, param.setf(item), item.title(), param.get(item), circle=good.color)
		
			accordion = Accordion(children=[HBox(list(param.element.values()))])
			accordion.set_title(0, param.title)
			accordion.add_class('helipad_param_peritem')
			return accordion
		
		self.model.doHooks('CpanelTop', [self, None])
	
		#Global config
		for param in model.params.values():
			if not getattr(param, 'config', False): continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
			if param.name=='csv': param.set('filename')
			if param.type=='checkentry' and getattr(param, 'func', None) is None: param.set(False)
		
		self.model.doHooks('CpanelAboveItemParams', [self, None])
		
		#Per-good parameters
		for param in model.goodParams.values():
			display(constructAccordion(param, model.nonMoneyGoods))
	
		#Per-breed parameters
		for prim in model.primitives.values():
			for param in prim.breedParams.values():
				display(constructAccordion(param, prim.breeds))
		
		self.model.doHooks('CpanelAboveParams', [self, None])
	
		#Global parameters
		for param in model.params.values():
			if getattr(param, 'config', False) or param.type=='checkgrid': continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
		
		#Checkgrids
		for param in model.params.values():
			if param.type!='checkgrid': continue
			acc = renderParam(param, None, param.title, None)
			if acc is not None: display(acc)
		
		self.model.doHooks('CpanelAbovePlotList', [self, None])
		
		#Plots
		def func(self, val): self.selected = val
		Plot.set = func
		children = []
		for plot in model.plots.values():
			plot.element = interactive(plot.set, val=plot.selected)
			plot.element.children[0].description = plot.label
			children.append(plot.element)
		pacc = Accordion(children=[HBox(children)])
		pacc.set_title(0, 'Plots')
		pacc.add_class('helipad_checkgrid')
		display(pacc)
		
		self.model.doHooks('CpanelAboveShocks', [self, None])
		
		#Shocks
		if len(model.shocks.shocks):
			def sfunc(self, val): self.active = val
			def sfuncButton(slef, *args): slef.do(self.model)
			model.shocks.Shock.set = sfunc
			model.shocks.Shock.setButton = sfuncButton
			children = []
			for shock in model.shocks.shocksExceptButtons.values():
				shock.element = interactive(shock.set, val=shock.active)
				shock.element.children[0].description = shock.name
				shock.element.children[0].description_tooltip = shock.desc if shock.desc is not None else ''
				children.append(shock.element)
			buttons = []
			for shock in model.shocks.buttons.values():
				shock.element = Button(description=shock.name, icon='bolt')
				shock.element.click = shock.setButton
				shock.element.description_tooltip = shock.desc if shock.desc is not None else ''
				buttons.append(shock.element)
			children.append(HBox(buttons))
			sacc = Accordion(children=[VBox(children)])
			sacc.set_title(0, 'Shocks')
			display(sacc)
		
		self.model.doHooks('CpanelBottom', [self, None])
		
		#Model flow control: pause/run button
		@model.hook(prioritize=True)
		def plotsPreLaunch(model):
			self.startstop = Button(description='Pause', icon='pause')
			self.startstop.click = self.model.stop
			display(self.startstop)
			
		#Disable stopafter and csv if it's plotless; otherwise we'll have no way to stop the model
		@model.hook(prioritize=True)
		def plotsLaunch(model, graph):
			if graph is None:
				for e in model.params['stopafter'].element.children + model.params['csv'].element.children:
					e.disabled = True
		
		@model.hook(prioritize=True)
		def modelStop(model):
			self.startstop.click = self.model.start
			self.startstop.description = 'Run'
			self.startstop.icon = 'play'
					
		@model.hook(prioritize=True)
		def modelStart(model, hasModel):
			self.startstop.click = self.model.stop
			self.startstop.description = 'Pause'
			self.startstop.icon = 'pause'
			
			#Disable non-runtime elements
			for p in self.model.allParams:
				if not p.runtime:
					for e in (p.element.values() if isinstance(p.element, dict) else [p.element]):
						for c in e.children: c.disabled = True
			for p in self.model.plots.values():
				p.element.children[0].disabled = True
		
		@model.hook(prioritize=True)
		def terminate(model, data):
			self.startstop.layout.visibility = 'hidden'
			
			#Re-enable control panel elements
			for p in self.model.allParams:
				if p.type == 'hidden' or (p.type=='checkentry' and getattr(p, 'func', None) is not None): continue
				for e in (p.element.values() if isinstance(p.element, dict) else [p.element]):
					e.children[0].disabled = False
					if p.type=='checkentry' and p.get():
						e.children[1].disabled = False
			for p in self.model.plots.values():
				p.element.children[0].disabled = False