import os
import symtable

from utils import qual_name_from_path
from tokens import Package, Class, Function, Component, Dependency, DepenType


class ProjectNameSpace:
    """
    Manages all names defined in the source code of the project.
    Creates the component tree and the namespace of defined names.
    """

    def __init__(self, root_dir: str):
        self.gid = 0
        self.root_comp = None
        self.rel_tokens = {}  # lookup table <gid, token>
        self.tokens = {}  # lookup table <qualified_name, token>

        self.relations = {
            # dependencies/associations are all relations, stores for every token the relations of its children
            'dependencies': set(),
            'associations': set()
        }

        self._build_namespace(root_dir)  # initialize namespace with names declared in source

    def get_comp_tree_dict(self):
        return self.root_comp.to_dict()

    def _build_namespace(self, root_dir):
        """
        Creates initial namespace of names defined in source by traversing the directory tree of root_dir backwards.
        Reads regular packages, namespace packages, modules, classes and functions defined in source.
        Creates component tokens from regular packages and modules; creates package tokens from namespace packages.
        Determines names defined in every component/package current_token.
        Sorts tokens into current_token tree in order to provide means to easily persist tokens to JSON.

        :param root_dir: Name of root directory
        :type: string
        """
        for current_dir, sub_dirs, files in os.walk(root_dir, topdown=False):
            if '__init__.py' in files:  # current_dir is regular package
                current = self._make_component(current_dir)
                self._parse_file_content(current_dir, '__init__.py', current)
            else:  # current_dir is namespace package
                current = self._make_package(current_dir)

            has_children = False
            for file in files:
                if file.endswith('.py') and file != '__init__.py':
                    comp = self._make_component(current_dir, file)
                    self._parse_file_content(current_dir, file, comp)
                    if len(comp.classes) == 0 and len(comp.functions) == 0:
                        self.tokens.pop(comp.qual_name)
                    else:
                        current.components.add(comp)
                        has_children = True

            for sub_dir in sub_dirs:
                try:
                    qual_name = qual_name_from_path(os.path.join(current_dir, sub_dir))
                    child = self.tokens[qual_name]
                    if isinstance(child, Component):
                        current.components.add(child)
                    elif isinstance(child, Package):
                        current.packages.add(child)
                    has_children = True
                except KeyError:
                    pass

            if not has_children:
                self.tokens.pop(current.qual_name)

            if current_dir == root_dir:
                self.root_comp = current

    def _make_package(self, directory):
        """
        Creates a Package Token from folder and adds it to self.tokens.

        :param directory: Name of directory
        :type directory: string
        :return: Package
        """
        qual_name = qual_name_from_path(directory)
        pkg = Package(self.gid, qual_name)
        self.tokens[qual_name] = pkg
        self.rel_tokens[self.gid] = pkg
        self.gid += 1
        return pkg

    def _make_component(self, directory, file=None):
        """
        Creates a Component Token from a directory containing an __init__.py or a file.
        Adds the Component to self.tokens.

        :param directory: Name of directory
        :type directory: string
        :return: Component
        """
        qual_name = qual_name_from_path(directory, file)
        comp = Component(self.gid, qual_name)

        if file is None:  # file is __init__.py --> parsing regular package
            comp.regular_pkg = True

        self.tokens[qual_name] = comp
        self.rel_tokens[self.gid] = comp
        self.gid += 1
        return comp

    def _parse_file_content(self, directory, file, component):
        """
        Reads the contents of file and adds Class and Function Tokens to component.

        :param directory: Name of directory
        :type directory: string
        :param file: Name of file
        :type file: string
        :param component: Module to add content to
        :type component: Component
        """
        with open(os.path.join(directory, file)) as f:
            comp_table = symtable.symtable(f.read(), file, 'exec')

            for child in comp_table.get_children():
                qual_name = component.qual_name + '.' + child.get_name()

                if child.get_type() == 'class':
                    cls = Class(self.gid, qual_name)
                    component.classes.add(cls)
                    component.declared_names[cls.name] = qual_name
                    self.tokens[qual_name] = cls
                    self.rel_tokens[self.gid] = cls
                    self.gid += 1

                    # parse class methods
                    for meth_table in child.get_children():
                        if meth_table.get_type() == 'function':
                            meth_qual_name = qual_name + '.' + meth_table.get_name()
                            meth = Function(self.gid, meth_qual_name, meth_table.get_parameters())
                            cls.declared_names[meth.name] = meth_qual_name
                            cls.inst_methods.add(meth)
                            self.tokens[meth_qual_name] = meth
                            self.rel_tokens[self.gid] = meth
                            self.gid += 1
                elif child.get_type() == 'function':  # child is component function
                    meth = Function(self.gid, qual_name, child.get_parameters())
                    component.functions.add(meth)
                    component.declared_names[meth.name] = qual_name
                    self.tokens[qual_name] = meth
                    self.rel_tokens[self.gid] = meth
                    self.gid += 1

    @property
    def dependencies(self):
        return self.relations['dependencies']

    @property
    def associations(self):
        return self.relations['associations']

    def get_parent(self, token):
        if '.' not in token.qual_name:
            return None
        else:
            qual_name = '.'.join(token.qual_name.split('.')[:-1])
            return self.tokens[qual_name]

    def get_token_of_local_name(self, token, name):
        """
        Tries to find name in the namespace of token.
        If name is local qualified name (e.g. of imported class) then first resolve prefix to
        component token and look in its namespace to find the remaining name.

        :param token:
        :param name:
        :return:
        """
        if '.' in name:  # prefixed name
            names = name.split('.')
            if len(names) == 2:  # function/class of imported module
                comp = self._find_in_token_hierarchy(token, names[0])  # find component from prefix
                if comp:
                    return self._find_in_token_hierarchy(comp, names[1])
        else:
            return self._find_in_token_hierarchy(token, name)

    def _find_in_token_hierarchy(self, token, name):
        """
        Tries to find name in the namespaces of tokens.
        Starting at token, it checks its hierarchy bottom up.
        E.g. if token is a method we check itself, its parent class and parent module.

        :param token: Token where name is used.
        :type token: Token
        :param name: Accessed name
        :type name: String
        :return: Token | None
        """
        qual_name_list = token.qual_name.split('.')
        lvls = range(len(qual_name_list) + 1)
        for lvl in reversed(lvls):
            lvl_qual_name = '.'.join(qual_name_list[:lvl])

            if lvl_qual_name:
                lvl_token = self.tokens[lvl_qual_name]
                if type(lvl_token) == Package:  # namespace packages do not declare/import names
                    return None

                qual_name = lvl_token.get_qualname_of_local_name(name)
                if qual_name:
                    return self.tokens[qual_name]
            # else: ascended to many levels without finding name

        return None

    def condense_relations(self):
        for rel in self.dependencies | self.associations:
            src = self.rel_tokens[rel.src_id]
            trgt = self.rel_tokens[rel.tgt_id]
            self._bubble_relation(src, trgt)

    def _bubble_relation(self, src, trgt):
        """
        :param src:
        :type src: Token
        :param trgt:
        :type trgt: Token
        :return:
        """
        src_parent = self.get_parent(src)
        trgt_parent = self.get_parent(trgt)

        if src_parent and trgt_parent:
            if src_parent == trgt_parent:  # src/trgt are contained in same component
                dep = Dependency(src.gid, trgt.gid, DepenType.USES)
                self.dependencies.add(dep)
                self.tokens[src_parent.qual_name].relations.add(dep)
            else:
                self._bubble_relation(src_parent, trgt_parent)
        else:
            pass
