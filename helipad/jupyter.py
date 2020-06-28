from ipywidgets import interactive, Layout, Accordion, HBox, VBox, HTML
from IPython.display import display

class JupyterInterface:
	def __init__(self, model):
		self.model = model
		
		#CSS niceties
		display(HTML(value="""<style type="text/css">
			.helipad_circle{
				height: 10px; width: 10px;
				border-radius: 10px;
				border: 1px solid rgba(0,0,0,0.2);
				display: inline-block;
				margin-right:5px;
			}
		</style>"""))
		
		def constructElement(param, func, title, val, circle=None):
			i=None
			if param.type=='slider':
				i = interactive(func, val=(param.opts['low'],param.opts['high'], param.opts['step']))
			elif param.type=='check':
				i = interactive(func, val=val)
			elif param.type=='menu':
				i = interactive(func, val=[(k[1], k[0]) for k in param.opts.items()])
			elif param.type=='checkentry':
				i = interactive(func, b=isinstance(val, str) or val, s=val if isinstance(val, str) else '')
				if val==False: i.children[1].disabled = True
				i.children[1].description = ''
	
			if i is not None:
				circle='<span class="helipad_circle" style="background:'+circle.hex_l+'"></span>' if circle is not None else ''
				i.children[0].description = circle+title
				i.children[0].style = {'description_width': 'initial'} #Don't truncate the label
				i.children[0].description_tooltip = param.desc if param.desc is not None else ''
				if param.type!='checkentry': i.children[0].value = val
	
			return i
		
		def constructAccordion(param, itemList):
			param.element = {}
			for item, good in itemList.items():
				param.element[item] = constructElement(param, param.setf(item), item.title(), param.get(item), circle=good.color)
		
			i,hboxes,elements=(0,[],list(param.element.values()))
			while 2*i<len(elements):
				hboxes.append(HBox([elements[2*i], elements[2*i+1]] if len(elements)>2*i+1 else [elements[2*i]]))
				i+=1
		
			accordion = Accordion(children=[VBox(hboxes)])
			accordion.set_title(0, param.title)
			return accordion
	
		#Per-good parameters
		for param in model.goodParams.values():
			display(constructAccordion(param, model.nonMoneyGoods))
	
		#Per-breed parameters
		for prim in model.primitives.values():
			for param in prim.breedParams.values():
				display(constructAccordion(param, prim.breeds))
	
		#Global parameters
		for param in model.params.values():
			param.element = constructElement(param, param.setf(), param.title, param.get())
			if param.element is not None: display(param.element)