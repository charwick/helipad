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
				i = interactive(func, b=isinstance(val, param.entryType) or val, s=str(val) if isinstance(val, param.entryType) else '')
				if param.obj is None:
					i = HBox(i.children)
					i.children[0].layout = Layout(width='150px')
				if val==False: i.children[1].disabled = True
				i.children[1].description = ''
	
			if i is not None:
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
		
			i,hboxes,elements=(0,[],list(param.element.values()))
			while 2*i<len(elements):
				hboxes.append(HBox([elements[2*i], elements[2*i+1]] if len(elements)>2*i+1 else [elements[2*i]]))
				i+=1
		
			accordion = Accordion(children=[VBox(hboxes)])
			accordion.set_title(0, param.title)
			return accordion
		
		self.model.doHooks('CpanelTop', [self, None])
	
		#Global config
		for param in model.params.values():
			if not getattr(param, 'config', False): continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
			if param.name=='csv': param.set('filename')
			if param.type=='checkentry': param.set(False)
		
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
			if getattr(param, 'config', False): continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
		
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
		
		if len(model.shocks.shocks):
			def sfunc(self, val): self.active = val
			model.shocks.Shock.set = sfunc
			children = []
			for shock in model.shocks.shocks.values():
				i = interactive(shock.set, val=shock.active)
				i.children[0].description = shock.name
				i.children[0].description_tooltip = shock.desc if shock.desc is not None else ''
				children.append(i)
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
			
			#Re-enable non-runtime elements
			for p in self.model.allParams:
				if not p.runtime:
					for e in (p.element.values() if isinstance(p.element, dict) else [p.element]):
						e.children[0].disabled = False
						if p.type=='checkentry' and p.get():
							e.children[1].disabled = False
			for p in self.model.plots.values():
				p.element.children[0].disabled = False