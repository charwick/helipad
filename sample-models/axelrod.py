# Replicates the repeated PD tournament from Axelrod (1980)
# Paper here: https://www.jstor.org/stable/173932
# Strategies indexed here: https://axelrod.readthedocs.io/en/stable/reference/overview_of_strategies.html#axelrod-s-first-tournament
# Strategies requiring chi-squared tests for randomness or such not yet implemented
# Difference from the original: The tournament matches stochastically, rather than being a round-robin, and repeats.

#===============
# SETUP
#===============

from helipad import Helipad
from helipad.gui import checkGrid
import numpy.random as random
from numpy import mean

heli = Helipad()
heli.name = 'Axelrod Tournament'
heli.order = 'match'

heli.params['agents_agent'].type = 'hidden' #So we can postpone breed determination until the end

#Initial parameter values match the payoffs in Table 1
heli.addParameter('cc', 'C-C payoff', 'slider', dflt=3, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('dc', 'D-C payoff', 'slider', dflt=5, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('cd', 'C-D payoff', 'slider', dflt=0, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('dd', 'D-D payoff', 'slider', dflt=1, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('rounds', 'Rounds per period', 'slider', dflt=200, opts={'low': 10, 'high': 1000, 'step': 10})
heli.addParameter('n', 'Agents per strategy', 'slider', dflt=3, opts={'low': 1, 'high': 10, 'step': 1}, runtime=False)

def reset():
	for a in heli.agents['agent']: a.stocks['payoff'] = 0
heli.addButton('Reset Wealth', reset)

heli.addGood('payoff','009900')

#Store associated colors and default-checked state to cycle over later
strategies = {
	'alwaysCooperate': (True, '00CC00'),
	'alwaysDefect': (True, 'CC0000'),
	'randomly': (True, '006600'),
	'TFT': (True, 'CC9900', 'Cooperates on the first round and thereafter plays the move last played by the opponent.'),
	'Tullock': (False, '663311', 'Cooperates for the first 11 rounds then randomly cooperates 10% less often than the opponent has in the previous 10 rounds.'),
	'Nydegger': (False, '003399', 'A stooge which has a memory and appears to be trustworthy, potentially cooperative, but not gullible.'),
	'Grofman': (False, '9999CC', 'Cooperates with probability 2/7 if the players did different things on the previous move, otherwise cooperates.'),
	'Shubik': (False, '666600', 'Punishes defection with an incrementing string of retaliations.'),
	'Grudger': (True, '000066', 'Cooperates until the opponent defects, and then defects thereafter'),
	'Davis': (False, '660000', 'Cooperates for 10 periods, and then plays Grudger.'),
	'Feld': (False, '000000', 'Plays tit-for-tat, but with P[Cooperate] declining to 0.5 as the rounds approach the end'),
	'Joss': (False, 'CCCCCC', 'Tit-For-Tat, except cooperation is only with 90% probability'),
}

#Build the strategies toggle
def GUIAbovePlotList(gui, bg):
	gui.model.strategies = checkGrid(parent=gui.parent, text='Strategies', columns=2, bg=bg)
	for s,v in strategies.items():
		gui.model.strategies.addCheck(s, s, v[0], v[2] if len(v)>=3 else None)
	return gui.model.strategies
heli.addHook('GUIAbovePlotList', GUIAbovePlotList)

#===============
# STRATEGIES
# Return True to cooperate, and False to defect.
#===============

def TFT(rnd, history, own):
	if not len(history): return True
	else: return history[-1]

def alwaysCooperate(rnd, history, own): return True

def alwaysDefect(rnd, history, own): return False

def randomly(rnd, history, own): return random.choice(2, 1)[0]

def Tullock(rnd, history, own):
	if len(history) < 11: return True
	rate = mean(history[-10:])-.1
	if rate < 0: rate = 0
	return random.choice(2, 1, p=[1-rate, rate])[0]

def Nydegger(rnd, history, own):
	if len(history) <= 2: return TFT(rnd, history, own)
	if len(history) == 3:
		if not history[0] and not own[1] and history[1]: return False
		else: return TFT(rnd, history, own)
		
	def a(i):
		n=0
		if not history[-i]: n += 2
		if not own[-i]: n += 1
		return n
	A = 16*a(1) + 4*a(2) + a(3)
	return A not in [1,6,7,17,22,23,26,29,30,31,33,38,39,45,49,54,55,58,61]

def Grofman(rnd, history, own):
	if not len(history): return True
	elif history[-1] ^ own[-1]: return random.choice(2, 1, p=[5/7, 2/7])[0]
	else: return True

def Shubik(rnd, history, own):
	k=0 #The number of rounds to retaliate
	rs=0 #the number of rounds I've already retaliated so far
	for r, me in enumerate(own):
		if me and not history[r]: k += 1 #Increment k every time the opponent defected while I wasn't retaliating
		if not me: rs += 1
		else: rs = 0 #Make sure we're only counting current retaliations
	
	if not len(history): return True 
	if not rs and not history[-1]: return False #Start retaliation if the opponent defected last period
	if rs and rs < k: return False #Keep retaliating if you've started a string of defections and haven't reached the limit
	return True

def Grudger(rnd, history, own):
	return False not in history

def Davis(rnd, history, own):
	if len(history) < 10: return True
	else: return Grudger(rnd, history, own)

def Feld(rnd, history, own):
	if not len(history): return True
	if not history[-1]: return False
	
	pDef = rnd/heli.param('rounds')/2
	return random.choice(2, 1, p=[pDef, 1-pDef])[0]

def Joss(rnd, history, own):
	if not len(history) or history[-1]: return random.choice(2, 1, p=[0.1, 0.9])[0]
	if not history[-1]: return False

#===============
# MODEL LOGIC
#===============

def match(agents, primitive, model, stage):
	h1, h2 = ([], [])
	for rnd in range(int(model.param('rounds'))):
		#Play
		response1 = globals()[agents[0].breed](rnd, h2, h1)
		response2 = globals()[agents[1].breed](rnd, h1, h2)
		h1.append(response1)
		h2.append(response2)
	
		#Payoffs
		agents[0].stocks['payoff'] += model.param(('c' if response1 else 'd') + ('c' if response2 else 'd'))
		agents[1].stocks['payoff'] += model.param(('c' if response2 else 'd') + ('c' if response1 else 'd'))
			
heli.addHook('match', match)

#Add breeds last-minute so we can toggle them in the control panel
def modelPreSetup(model):
	
	#Clear breeds from the previous run
	for b in model.primitives['agent'].breeds:
		model.data.removeReporter(b+'-proportion')
	model.primitives['agent'].breeds = {}
	
	model.strategies.disable()
	for k,v in model.strategies.items():
		if v.get(): model.addBreed(k, strategies[k][1])
	
	model.param('agents_agent', len(model.primitives['agent'].breeds)*model.param('n')) #Three of each strategy, for speed
	
	for b, d in model.primitives['agent'].breeds.items():
		model.data.addReporter(b+'-proportion', proportionReporter(b))
		model.addSeries('payoffs', b+'-proportion', b, d.color)
heli.addHook('modelPreSetup', modelPreSetup)

def terminate(gui, data):
	gui.model.strategies.enable()
heli.addHook('terminate', terminate)

#===============
# CONFIGURATION
#===============

#Tally up the total payoff once each period, so we don't have to do it on every agent
def dataCollect(data, t):
	data.model.totalP = data.agentReporter('stocks', good='payoff', stat='sum')(data.model)
heli.addHook('dataCollect', dataCollect)

def proportionReporter(breed):
	def func(model):
		return model.data.agentReporter('stocks', breed=breed, good='payoff', stat='sum')(model)/model.totalP
	return func

heli.addPlot('payoffs', 'Payoffs')

#===============
# LAUNCH THE GUI
#===============

heli.launchGUI()