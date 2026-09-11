"""Tiny drawing fixtures for contract tests, never used by the live director."""
from copy import deepcopy

def visual_fixture():
    recipe={'size':[16,24],'layers':[['rect',5,2,6,6,'accent'],['rect',3,8,10,10,'#6688aa'],['rect',4,18,3,5,'shadow'],['rect',9,18,3,5,'shadow']]}
    return {'style':'isolated test geometry','terrain':'metal','palette':{'ground':'#142030','path':'#344458','water':'#091221','wall':'#202b40','accent':'#70ffff','shadow':'#050912'},'sprites':{key:deepcopy(recipe) for key in ('hero','npc','enemy','building','vegetation','object')},'scenery':[],'density':0}
