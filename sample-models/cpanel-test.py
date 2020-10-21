#This is not a model and will not run. It does, however, register parameters of every available type in order to test the rendering of the control panel.

#===============
# PREAMBLE
#===============

from helipad import Helipad
# from utility import CobbDouglas

heli = Helipad()
heli.name = 'Test'

#A handful of breeds and goods
breeds = [
	('hobbit', 'jam', '#D73229'),
	('dwarf', 'axe', '#2D8DBE'),
	('elf', 'lembas', '#CCBB22')
]
AgentGoods = {}
for b in breeds:
	heli.addBreed(b[0], b[2], prim='agent')
	heli.addGood(b[1], b[2])

def gcallback(model, name, val):
	print(name, '=', val)

def icallback(model, name, item, val):
	print(name, '/', item, '=', val)

#===============
# ADD PARAMETERS
#===============

heli.addParameter('gslider', 'Global slider', 'slider', dflt=1.5, opts={'low': 1, 'high': 5, 'step': 0.1}, callback=gcallback)
heli.addParameter('gcheck', 'Global check', 'check', dflt=True, callback=gcallback)
heli.addParameter('gmenu', 'Global menu', 'menu', dflt='two', opts={
	'one': 'Option one',
	'two': 'Option two',
	'three': 'Option three'
}, callback=gcallback)
heli.addParameter('gcheckentry', 'Global Checkentry', 'checkentry', dflt='They\'re taking the hobbits to Isengard', callback=gcallback)
heli.addParameter('glogslider', 'Global Logslider', 'slider', dflt=8, opts=[1,2,3,5,8,13,21,34], callback=gcallback)

heli.addBreedParam('islider', 'Item Slider', 'slider', dflt={'hobbit': 0.1, 'dwarf': 0.3}, opts={'low':0, 'high': 1, 'step': 0.01}, desc='A slider that takes a value for each breed', callback=icallback)
heli.addGoodParam('icheck', 'Item Check', 'check', dflt={'jam': False, 'axe': True}, callback=icallback)
heli.addBreedParam('imenu', 'Item Menu', 'menu', dflt={'hobbit': 'three', 'dwarf': 'two'}, opts={
	'one': 'Option one',
	'two': 'Option two',
	'three': 'Option three'
}, desc='A menu that takes a value for each breed', callback=icallback)
heli.addGoodParam('icheckentry', 'Item Checkentry', 'checkentry', dflt={'jam': False, 'axe': 'wood'}, callback=icallback)
# heli.addGoodParam('ilogslider', 'Item Logslider', 'slider', dflt={'axe': 5, 'lembas': 21}, opts=[1,2,3,5,8,13,21,34], callback=icallback)

heli.addParameter('gcheckgrid', 'Global Checkgrid', 'checkgrid',
	opts={'gondor':('Gondor', 'Currently calling for aid'), 'isengard':'Isengard', 'rohan':'Rohan', 'rivendell':'Rivendell', 'khazad':('Khazad-dûm', 'Nice diacritic')},
	dflt=['gondor', 'rohan', 'khazad'], callback=gcallback
)

#===============
# LAUNCH
#===============

heli.launchCpanel()