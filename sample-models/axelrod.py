# Replicates the repeated PD tournament from Axelrod (1980)
# Paper here: https://www.jstor.org/stable/173932
# Strategies indexed here: https://axelrod.readthedocs.io/en/stable/reference/overview_of_strategies.html#axelrod-s-first-tournament
# Difference from the original: The tournament matches stochastically, rather than being a round-robin, and repeats.

#===============
# SETUP
#===============

from helipad import Helipad
import numpy.random as random
from numpy import mean

heli = Helipad()
heli.order = 'match'

#Initial parameter values match the payoffs in Table 1
heli.addParameter('cc', 'C-C payoff', 'slider', dflt=3, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('dc', 'D-C payoff', 'slider', dflt=5, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('cd', 'C-D payoff', 'slider', dflt=0, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('dd', 'D-D payoff', 'slider', dflt=1, opts={'low': 0, 'high': 10, 'step': 0.5})
heli.addParameter('rounds', 'Rounds per period', 'slider', dflt=200, opts={'low': 10, 'high': 1000, 'step': 10})

heli.addGood('payoff','009900')

heli.addBreed('alwaysCooperate', '00CC00')
heli.addBreed('alwaysDefect', 'CC0000')
heli.addBreed('randomly', '006600')
heli.addBreed('TFT', 'CC9900')
heli.addBreed('Tullock', '663311')
heli.addBreed('Nydegger', '003399')
heli.addBreed('Grofman', '9999CC')

#===============
# STRATEGIES
# Return True to cooperate, and False to defect.
#===============

#Cooperates on the first round, and then does whatever the opponent did in the last round.
def TFT(history, own):
	if not len(history): return True
	else: return history[-1]

def alwaysCooperate(history, own): return True

def alwaysDefect(history, own): return False

def randomly(history, own): return random.choice([0, 1], size=1)[0]

#Cooperates for the first 11 rounds then randomly cooperates 10% less often than the opponent has in the previous 10 rounds.
def Tullock(history, own):
	if len(history) < 11: return True
	rate = mean(history[-10:])-.1
	if rate < 0: rate = 0
	return random.choice([0, 1], size=1, p=[1-rate, rate])[0]

def Nydegger(history, own):
	if len(history) <= 2: return TFT(history, own)
	if len(history) == 3:
		if not history[0] and not own[1] and history[1]: return False
		else: return TFT(history, own)
		
	def a(i):
		n=0
		if not history[-i]: n += 2
		if not own[-i]: n += 1
		return n
	A = 16*a(1) + 4*a(2) + a(3)
	return A not in [1,6,7,17,22,23,26,29,30,31,33,38,39,45,49,54,55,58,61]

def Grofman(history, own):
	if not len(history): return True
	elif history[-1] ^ own[-1]: return random.choice([0, 1], size=1, p=[5/7, 2/7])[0]
	else: return True

#===============
# MODEL LOGIC
#===============

def match(agents, primitive, model, stage):
	h1, h2 = ([], [])
	for i in range(int(model.param('rounds'))):
		#Play
		response1 = globals()[agents[0].breed](h2, h1)
		response2 = globals()[agents[1].breed](h1, h2)
		h1.append(response1)
		h2.append(response2)
	
		#Payoffs
		agents[0].goods['payoff'] += model.param(('c' if response1 else 'd') + ('c' if response2 else 'd'))
		agents[1].goods['payoff'] += model.param(('c' if response2 else 'd') + ('c' if response1 else 'd'))
			
heli.addHook('match', match)

#===============
# CONFIGURATION
#===============

#Tally up the total payoff once each period, so we don't have to do it on every agent
def dataCollect(data, t):
	data.model.totalP = data.agentReporter('goods', good='payoff', stat='sum')(data.model)
heli.addHook('dataCollect', dataCollect)

def proportionReporter(breed):
	def func(model):
		return model.data.agentReporter('goods', breed=breed, good='payoff', stat='sum')(model)/model.totalP
	return func

heli.addPlot('payoffs', 'Payoffs')
for b, d in heli.primitives['agent']['breeds'].items():
	heli.data.addReporter(b+'-proportion', proportionReporter(b))
	heli.addSeries('payoffs', b+'-proportion', b, d.color)

#===============
# LAUNCH THE GUI
#===============

heli.launchGUI()