from ipywidgets import interactive, Layout, Accordion, HBox, VBox, HTML, Label
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
	
		#Global config
		for param in model.params.values():
			if not getattr(param, 'config', False): continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
			if param.name=='csv': param.set('filename')
			if param.type=='checkentry': param.set(False)
		
		#Per-good parameters
		for param in model.goodParams.values():
			display(constructAccordion(param, model.nonMoneyGoods))
	
		#Per-breed parameters
		for prim in model.primitives.values():
			for param in prim.breedParams.values():
				display(constructAccordion(param, prim.breeds))
	
		#Global parameters
		for param in model.params.values():
			if getattr(param, 'config', False): continue
			param.element = renderParam(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)
		
		#Plots
		def func(self, val): self.selected = val
		Plot.set = func
		children, hboxes = ([],[])
		for name, plot in model.plots.items():
			i = interactive(plot.set, val=plot.selected)
			i.children[0].description = plot.label
			children.append(i)
		acc = Accordion(children=[HBox(children)])
		acc.set_title(0, 'Plots')
		acc.add_class('helipad_checkgrid')
		display(acc)
			