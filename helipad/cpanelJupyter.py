"""
The control panel class for use in Jupyter notebooks. This module should not be imported directly; use `model.launchCpanel()` instead.
"""

import os
from collections import ChainMap
from ipywidgets import interactive, Layout, Accordion, HBox, VBox, HTML, Label, Button, FloatProgress
from IPython.display import display
from helipad.param import Param
from helipad.helpers import ï

class Cpanel(VBox):
	"""The control panel class for use in Jupyter notebooks. https://helipad.dev/functions/cpanel/"""
	def __init__(self, model, redraw: bool=False):
		super().__init__()
		self.model = model
		if redraw:
			self.children = ()
			self.remove_class('invalid')
		else: self.add_class('helipad_cpanel')
		self.valid = True

		#CSS niceties
		__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
		with open(os.path.join(__location__,'ipy-styles.css'), encoding='UTF-8') as c: css = c.read()

		#CSS for goods and breeds, since Ipywidgets ≥8.0 oversanitizes HTML in description attributes
		for n,c in ChainMap(*[{f'breed_{p}_{k}': v.color.hex for k,v in d.breeds.items()} for p,d in model.agents.items()]+[{'good_'+k: v.color.hex for k,v in model.goods.items()}]).items():
			css += f'.helipad_{n} .widget-label::before {{ background: {c} }}'

		self.children += HTML(value='<style type="text/css">'+css+'</style>'),

		#Callback function generator for Jupyter elements
		def setVar(param, item=None):
			def sv(val): #Ipywidgets bases on the function signature, so can't use more than one here…
				if param.type=='checkgrid': param.set(item, val, updateGUI=False)
				else: param.set(val, item, updateGUI=False)

				if callable(param.callback):
					if param.per is None:
						pval = param.get(item) if param.type != 'checkgrid' else (item, param.get(item))
						param.callback(self.model, param.name, pval)
					else: param.callback(self.model, param.name, item, param.get(item))

			#Consolidate value from bool and string, and toggle entry disabled state
			#Have to return a different function since Ipywidgets bases the interactive off the function signature
			if param.type=='checkentry':
				def sv2(b: bool, s: str):
					#Ipywidgets ≥8.0 runs the callback before the element is assigned
					try:
						els = param.element if item is None else param.elements[item]
						els.children[1].disabled = not b
					except (AttributeError, KeyError): return

					#Coercing an int can fail, so if there's an exception, reset the textbox content
					try:
						val = s if (b and s=='') or 'func〈' in s else (param.entryType(s) if b else False)
						sv(val)
					except: els.children[1].value = str(param.get())

				return sv2
			else: return sv
		Param.setVar = setVar

		def renderParam(param, func, title: str, val, circle=None):
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
				if param.per is None:
					i = HBox(i.children)
					i.children[0].layout = Layout(width='150px')
				if val is False: i.children[1].disabled = True
				i.children[1].description = ''

				if param.name=='stopafter' and param.event:
					i.children[0].disabled = True
					i.children[1].disabled = True
					i.add_class('helipad_checkentry_func')
			elif param.type=='checkgrid':
				param.elements = {}
				for k,v in param.opts.items():
					if not isinstance(v, (tuple, list)): v = (v, None)
					elif len(v) < 2: v = (v[0], None)
					param.elements[k] = interactive(param.setVar(k), val=param.vars[k])
					param.elements[k].children[0].description = v[0]
					param.elements[k].children[0].description_tooltip = v[1] if v[1] is not None else '' #Not working, not sure why

				#Toggle-all button
				#Would like to put it in .p-Collapse-header, but I don't think I can place an element in there
				#So append it to the children and we'll absolutely position it to the right place
				param.elements['toggleAll'] = Button(icon='check')
				def toggleAll(b=None):
					v = False if [c.children[0].value for c in param.element.children[0].children if not isinstance(c, Button) and c.children[0].value] else True
					for c in param.element.children[0].children:
						if not isinstance(c, Button) and not c.children[0].disabled: c.children[0].value = v
				param.elements['toggleAll'].on_click(toggleAll)
				param.elements['toggleAll'].add_class('helipad_toggleAll')

				param.containerElement = HBox(list(param.elements.values()))
				i = Accordion(children=[param.containerElement], selected_index=0)
				i.set_title(0, title)
				i.add_class('helipad_checkgrid')

			if i is not None and param.type!='checkgrid':
				if param.per is not None:
					n = (f'{param.prim}_' if param.per=='breed' else '')+title.lower()
					i.children[0].add_class(f'helipad_{param.per}_{n}')
					i.children[0].add_class('helipad_per_item')
				i.children[0].description = title
				i.children[0].style = {'description_width': 'initial'} #Don't truncate the label
				i.children[0].description_tooltip = param.desc if param.desc is not None else ''
				if param.type=='slider' and isinstance(param.opts, list):
					i.children[0].add_class('widget-logslider')
					i.children[1].value = str(val)
					if val in param.opts: val=param.opts.index(val)
				if param.type!='checkentry': i.children[0].value = val

			return i

		def constructAccordion(param, itemList: dict):
			param.elements = {}
			for item, good in itemList.items():
				param.elements[item] = renderParam(param, param.setVar(item), item.title(), param.get(item), circle=good.color)

			accordion = Accordion(children=[HBox(list(param.elements.values()))], selected_index=0)
			accordion.set_title(0, param.title)
			accordion.add_class('helipad_param_peritem helipad_paramgroup')
			return accordion

		ctop = self.model.doHooks('CpanelTop', [self, None])
		if ctop: self.children += ctop,

		#Global config
		for n,param in model.params.items():
			if not getattr(param, 'config', False) or param.type=='checkgrid': continue
			param.element = renderParam(param, param.setVar(), param.title, param.get())
			if param.element is not None: self.children += (param.element,)
			if param.name=='csv': param.set(ï('filename'))
			if n=='stopafter' and not param.event and not param.get(): param.element.children[1].value = '10000'
			if param.type=='checkentry' and getattr(param, 'config', False) and not (n=='stopafter' and param.event): param.set(False)

		caip = self.model.doHooks('CpanelAboveItemParams', [self, None])
		if caip: self.children += caip,

		#Per-good parameters
		for param in model.params.perGood.values():
			param.element = constructAccordion(param, model.goods.nonmonetary)
			self.children += param.element,

		#Per-breed parameters
		for param in model.params.perBreed.values():
			param.element = constructAccordion(param, param.pKeys)
			self.children += param.element,

		cap = self.model.doHooks('CpanelAboveParams', [self, None])
		if cap: self.children += cap,

		#Pull out grouped parameters
		groups = []
		for group in self.model.params.groups: groups += list(group.members.keys())

		#Global parameters
		for k, param in model.params.globals.items():
			if getattr(param, 'config', False) or k in groups or param.type=='checkgrid': continue
			param.element = renderParam(param, param.setVar(), param.title, param.get())
			if param.element is not None: self.children += param.element,

		#Param groups
		for group in model.params.groups:
			for param in group.members.values():
				param.element = renderParam(param, param.setVar(), param.title, param.get())
			group.element = Accordion(children=[HBox([p.element for p in group.members.values()])], selected_index=0 if group.open else None)
			group.element.set_title(0, group.title)
			group.element.add_class('helipad_paramgroup')
			self.children += group.element,

		#Checkgrids
		for param in model.params.values():
			if param.type!='checkgrid' or param.name=='shocks': continue
			param.element = renderParam(param, None, param.title, None)
			if param.element is not None: self.children += param.element,

		cas = self.model.doHooks('CpanelAboveShocks', [self, None])
		if cas: self.children += cas,

		#Shocks
		if len(model.shocks):
			def sfuncButton(slef, *args): slef.do(self.model)
			model.shocks.Shock.setButton = sfuncButton
			model.params['shocks'].elements = {}
			children = []
			for shock in model.shocks.shocksExceptButtons.values():
				shock.element = interactive(shock.setCallback, val=shock.selected)
				shock.element.children[0].description = shock.name
				shock.element.children[0].description_tooltip = shock.desc if shock.desc is not None else ''
				children.append(shock.element)
				model.params['shocks'].elements[shock.name] = shock.element #For setting via model.param()
			buttons = []
			for shock in model.shocks.buttons.values():
				shock.element = Button(description=shock.name, icon='bolt')
				shock.element.click = shock.setButton
				shock.element.description_tooltip = shock.desc if shock.desc is not None else ''
				buttons.append(shock.element)
			children.append(HBox(buttons))
			model.params['shocks'].element = Accordion(children=[VBox(children)], selected_index=0)
			model.shocks.element = model.params['shocks'].element
			model.params['shocks'].element.set_title(0, model.params['shocks'].title)
			self.children += model.params['shocks'].element,

		cbot = self.model.doHooks('CpanelBottom', [self, None])
		if cbot: self.children += cbot,

		self.postinstruct = self.displayAlert(ï('After setting parameter values, run <code>launchVisual()</code> or <code>start()</code> to start the model.'))
		if not redraw:
			display(self)

			class progressBar(FloatProgress):
				def __init__(self):
					super().__init__(min=0, max=1)

				def determinate(self, det: bool):
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
					self2.description = ï('Pause')
					self2.icon = 'pause'

				def pause(self2):
					self2.click = self.model.start
					self2.description = ï('Run')
					self2.icon = 'play'

				def terminate(self):
					self.layout.visibility = 'hidden'

			#Remove previous hooks so we don't double up when re-running launchCpanel()
			model.hooks.remove('modelPreSetup', 'cpanel_visualPreLaunch')
			model.hooks.remove('terminate', 'cpanel_terminate')

			#Model flow control: pause/run button and progress bar
			@model.hook('modelPreSetup', prioritize=True)
			def cpanel_visualPreLaunch(model):
				self.runButton = runButton(description=ï('Pause'), icon='pause')
				self.progress = progressBar()
				self.postinstruct.layout = Layout(display='none')

				self.stopbutton = Button(description=ï('Stop'), icon='stop')
				self.stopbutton.click = self.model.terminate

				pbararea = HBox([self.runButton, self.stopbutton, self.progress])
				pbararea.add_class('helipad_progress_area')
				display(pbararea)

			@model.hook('terminate')
			def cpanel_terminate(model, data):
				self.postinstruct.layout = Layout(display='inline-block')
				self.stopbutton.layout.visibility = 'hidden'

	def displayAlert(self, text: str, inCpanel: bool=True):
		"""Display an alert element in the Jupyter notebook."""
		element = HTML(value=text)
		element.add_class('helipad_info') #Latter applies some built-in styles to the contents
		if inCpanel: self.children += element,
		else: display(element)
		return element

	def invalidate(self, message: str=ï('Model parameters changed, please re-launch the control panel with launchCpanel().')):
		"""Prevent the user from interacting with a control panel. A control panel is invalidated when another is launched."""
		self.valid = False
		self.add_class('invalid')
		warning = Label(value=message)
		warning.add_class('helipad_modal')
		self.children += warning,
		for p in self.model.params.values(): del p.element
		return warning

#https://stackoverflow.com/questions/24005221/ipython-notebook-early-exit-from-cell
class SilentExit(Exception):
	def _render_traceback_(self): pass