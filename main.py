#!/usr/bin/env python3
import json
import os

import parser

GO_EXEC = True
PROJECT_NAME = 'django'

if __name__ == '__main__':
    if GO_EXEC:
        os.chdir('python_parser')

    os.chdir('in')

    ns = parser.run(PROJECT_NAME)

    if GO_EXEC:
        os.chdir('..')

    os.chdir('../out')

    with open(PROJECT_NAME + '/package_tree.json', 'w') as f:
        json.dump(ns.get_comp_tree_dict(), f)
    with open(PROJECT_NAME + '/relations.json', 'w') as f:
        json.dump(ns.get_rel_dict(), f)
