#!/usr/bin/env python3
import json
import os

import parser

GO_EXEC = False
PROJECT_NAME = 'django'

if __name__ == '__main__':
    if GO_EXEC:
        os.chdir('in')
    else:
        os.chdir('../in/')

    ns = parser.run(PROJECT_NAME)

    os.chdir('../out')

    with open(PROJECT_NAME + '/component_tree.json', 'w') as f:
        json.dump(ns.get_comp_tree_dict(), f)
    with open(PROJECT_NAME + '/relations.json', 'w') as f:
        json.dump(ns.get_rel_dict(), f)
