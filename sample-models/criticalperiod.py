#A reconstruction of Hurford (1991), "The Evolution of the Critical Period for Language Acquisition"
#https://www.sciencedirect.com/science/article/abs/pii/001002779190024X

from helipad import Helipad, Agent
import random
from numpy.random import choice
from numpy import mean

heli = Helipad()
heli.name = 'Critical Period'
heli.order = 'random'

heli.addParameter('pleio', 'Pleiotropy', 'slider', dflt=7, opts={'low': 0, 'high': 10, 'step': 1}, runtime=False)
heli.addParameter('acq', 'Acquisition from', 'menu', dflt='mother', opts={'mother': 'Mother', 'wholepop': 'Whole Population'})
heli.addParameter('condition', 'Language affects', 'menu', dflt='rep', opts={'rep': 'Reproduction', 'srv': 'Survival'})

heli.params['num_agent'].opts['step'] = 10 #Need it to be divisible by the number of life stages
heli.params['num_agent'].opts['low'] = 10
heli.param('num_agent', 30)

#Returns language capacity
def capacity(self, gene=None, age=None):
	if gene is None: gene = self.dominantLap
	if age is None: age=self.age
	
	start = (10-self.model.param('pleio'))*age
	l = sum(gene[start:start+10])
	return 0 if l<0 else l
Agent.capacity = capacity

@heli.hook
def modelPostSetup(model):
	model.births = 0 #Keep track so we can mutate every 30
	
#Initialize agent variables
@heli.hook
def agentInit(agent, model):
	agent.language = 0
	agent.dominantLap = [2*i%2-1 for i in range(100-9*model.param('pleio'))] #±1
	agent.recessivLap = [2*i%2-1 for i in range(100-9*model.param('pleio'))]
	agent.hasReproduced = False
	agent.age = agent.id%10

@heli.reporter
def adultLanguage(model):
	return mean([a.language for a in model.agents['agent'] if a.age>1])

@heli.hook
def modelPreStep(model):
	for a in model.agents['agent']: a.hasReproduced = False

#Select people to die in accidents
@heli.hook
def modelPostStep(model):
	if model.param('condition')=='srv':
		p = [((a.age+1)/(a.language+1))**3 for a in model.agents['agent']]
		p = [n/sum(p) for n in p] #Normalize probabilities to add up to 1
		for a in choice(model.agents['agent'], int(model.param('num_agent')/10), False, p): a.die() #Paper says "up to 3" die per period, but doesn't say how the "up to" is determined

#Learn language and die if old
@heli.hook
def agentStep(agent, model, stage):
	capacity = agent.capacity()
	if model.param('acq') == 'mother' or not agent.age:
		mother = agent.parent[0] if isinstance(agent.parent, list) else agent.parent #Dead agents are automatically removed from parent lists
		exemp = mother.language if mother is not None else 0
	else: exemp = adultLanguage(model)
	
	agent.language += capacity if exemp >= agent.language + capacity else (capacity + exemp-agent.language)/2
			
	if agent.age >= 9: agent.die()

#Replace dead agents
@heli.hook
def agentDie(agent):
	
	#Nominate parents with probability proportional to the cube of the language score, in the reproduction condition
	#Or with equal probability in the survival condition
	if heli.param('condition')=='rep':
		nominees = []
		for a in heli.agents['agent']:
			if a.hasReproduced or a.age<=1: continue
			for n in range(round(a.language**3+1)): nominees.append(a.id) #+1 because otherwise we start out with no one able to reproduce
	else: nominees = [a.id for a in heli.agents['agent'] if not a.hasReproduced and a.age>1]
	n1 = n2 = heli.agent(random.choice(nominees))
	while n1.id == n2.id: n2 = heli.agent(random.choice(nominees))
	
	#Complicated inheritance so do it manually
	baby = n1.reproduce(partners=[n2])
	parents = [n1, n2]
	for n in parents:
		n.gamete = []
		inp = [n.dominantLap, n.recessivLap]
		for i,v in enumerate(inp[1]):
			n.gamete.append(inp[random.randrange(len(inp))][i])
	mf = random.randrange(len(parents))
	baby.dominantLap = parents[mf].gamete
	baby.recessivLap = parents[not mf].gamete
	heli.births += 1
	
	#Mutate by flipping a bit in the dominant LAP once every 30 births
	if not heli.births%30:
		r = random.randrange(len(baby.dominantLap))
		baby.dominantLap[r] = -baby.dominantLap[r]

# @heli.event(repeat=True)
# def test(model): return model.t%100==95

#Visualization
from helipad.visualize import TimeSeries, Charts
viz = heli.useVisual(Charts)
# lplot = viz.addPlot('language', 'Language')
# lplot.addSeries('adultLanguage', 'Adult Language', 'blue')

# gplot = viz.addPlot('geno', 'Genotypes')
gchart = viz.addPlot('geno', 'Capacity by stage (dominant allele)')
gchart2 = viz.addPlot('rec', 'Capacity by stage (recessive allele)', horizontal=True)

def genoReporter(age, gene=False):
	def rep(model):
		return mean([a.capacity(gene=None if not gene else a.recessivLap, age=age) for a in model.agents['agent']])
	return rep
gcolors = ['F00', 'F03', 'F06', 'F09', 'F0C', 'C0F', '90F', '60F', '30F', '00F']
for age in range(10):
	heli.data.addReporter('geno-'+str(age), genoReporter(age))
	heli.data.addReporter('rec-'+str(age), genoReporter(age, gene='rec'))
	# gplot.addSeries('geno-'+str(age), 'Capacity age '+str(age), '#'+gcolors[age])
	gchart.addBar('geno-'+str(age), str(age), '#'+gcolors[age])
	gchart2.addBar('rec-'+str(age), str(age), '#'+gcolors[age])

heli.launchCpanel()