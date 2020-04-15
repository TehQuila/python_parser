#!/usr/bin/env python3
import json
import os

import parser

PROJECT_NAME = 'django'

# todo: use type declarations in method signatures
if __name__ == '__main__':
    os.chdir('../in/')

    ns = parser.run(PROJECT_NAME)

    os.chdir('../out')

    with open(PROJECT_NAME + '/component_tree.json', 'w') as f:
        json.dump(ns.get_comp_tree_dict(), f)
