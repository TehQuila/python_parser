import ast
import os

from projectnamespace import ProjectNameSpace
from tokens import Dependency, DepenType, Stereotype, Class, Var, Association, AssocType
from utils import qual_name_from_path


def run(root_dir):
    print("initializing namespaces...")
    ns = ProjectNameSpace(root_dir)
    print("... found " + str(len(ns.tokens.values())) + " declared components, classes and functions")

    # parsers have side-effects on tokens of namespace
    print("parsing imports...")
    print("... __all__ variables")
    AllParser(ns).run(root_dir, False)
    print("... import statements")
    ImportParser(ns).run(root_dir, False)

    print("parsing instance attributes...")
    InstanceAttributeParser(ns).run(root_dir)
    print("... found " + str(len(ns.associations)) + " associations")
    print("parsing inheritances...")
    InheritanceParser(ns).run(root_dir)
    print("parsing function calls...")
    CallParser(ns).run(root_dir)
    print("... found " + str(len(ns.dependencies)) + " dependencies")

    print("condensing relations...")
    ns.condense_relations()
    print("... total relations: " + str(len(ns.dependencies) + len(ns.associations)))

    return ns


class Parser(ast.NodeVisitor):
    """
    Base class implementing directory tree traversal of github repository and
    access to the stack of currently processed tokens of the given namespace.
    """
    def __init__(self, ns):
        self.ns = ns
        self.token_stack = []

    def walk_dir_tree(self, root_dir, topdown=True):
        """
        Walks the directory tree topdown, starting at root_dir.
        Opens every file, looks up the corresponding component token and visits its root ast-nodes.

        :param root_dir: Name of the root directory of the project
        :type root_dir: String
        :param topdown: Starting at root_dir or from bottom up.
        :return: None
        """
        for current_dir, _, files in os.walk(root_dir, topdown):
            for file in files:
                if file == '__init__.py':
                    qual_name = qual_name_from_path(current_dir)
                else:
                    qual_name = qual_name_from_path(current_dir, file)

                if qual_name in self.ns.tokens:
                    with open(os.path.join(current_dir, file)) as f:
                        self.token_stack.append(self.ns.tokens[qual_name])
                        self.visit(ast.parse(f.read()))
                        self.token_stack.pop()
                # else:   module was excluded in ProjectNamespace

    @property
    def current_comp(self):
        return self.token_stack[0]

    @property
    def current_cls(self):
        try:
            return self.token_stack[1]
        except IndexError:
            return None

    @property
    def current_meth(self):
        try:
            return self.token_stack[2]
        except IndexError:
            return None

    @property
    def current_token(self):
        return self.token_stack[-1]

    def descend(self, node):
        qual_name = self.current_token.qual_name + '.' + node.name
        if qual_name in self.ns.tokens:
            self.token_stack.append(self.ns.tokens[qual_name])
            self.generic_visit(node)
            self.token_stack.pop()


class IndeterministicParser(Parser):
    """
    Implements run behaviour for parsers which need to traverse the directory tree multiple times.
    For example when you need to analyse the return value of a function, so that you know the value of
    a variable, to which the call of the function is assigned.
    """
    def __init__(self, ns):
        super().__init__(ns)
        self.unresolved_nodes = self.prev_unresolved_nodes = 0

    def run(self, root_dir, topdown=True):
        while True:
            self.walk_dir_tree(root_dir, topdown)
            if self.unresolved_nodes == self.prev_unresolved_nodes:
                break
            else:
                print("... unresolved nodes: " + str(self.unresolved_nodes) + " previously: " + str(self.prev_unresolved_nodes))
                self.prev_unresolved_nodes = self.unresolved_nodes
                self.unresolved_nodes = 0

    def _build_qualified_from_name(self, node):
        """
        Builds the qualified name of the import statement of a name.

        :param node: Import node to process
        :type node: ast.ImportFrom
        :return: Qualified name of imported name as string
        """
        # if current_token is not component, remove function/class name as it is not part of from_mod
        qual_name = self.current_comp.qual_name
        # while not isinstance(self.ns.tokens[qual_name], Component):
        #     qual_name = '.'.join(qual_name.split('.')[:-1])

        # resolve from path to qualified name of module
        if node.module is None:  # from path is only relative
            from_mod = '.'.join(qual_name.split('.')[:-node.level])
        else:
            if node.level == 0:  # from path is absolute
                from_mod = node.module
            else:  # from path is relative with path to submodule
                if self.current_comp.regular_pkg:  # if import is in __init__.py, "." refers to folder
                    from_mod = qual_name + '.' + node.module
                else:  # if import is in module.py, "." refers to folder containing module
                    from_mod = '.'.join(qual_name.split('.')[:-node.level]) + '.' + node.module

        return from_mod


class DeterministicParser(Parser):
    """
    Implements run behaviour for parsers, which travers the directory tree a single time.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def run(self, root_dir, topdown=True):
        self.walk_dir_tree(root_dir, topdown)


class AllParser(IndeterministicParser):
    """
    Parses the __all__ variable of a module.
    Analyses direct assignments to __all__ and resolves imports of __all__,
    in order to analyse concatenated assignments.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == '__all__':
                from_mod = self._build_qualified_from_name(node)
                if alias.asname:
                    self.current_token.all_aliases[alias.asname] = self.ns.tokens[from_mod].all
                else:
                    self.current_token.all_aliases[alias.name] = self.ns.tokens[from_mod].all

    def _flatten_nested_tuple(self, tupl):
        return sum(([x] if not isinstance(x, tuple) else self._flatten_nested_tuple(x) for x in tupl), [])

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id == '__all__':
                    if isinstance(node.value, ast.List) or isinstance(node.value, ast.Tuple):
                        self.current_token.all = [el.s for el in node.value.elts]
                    elif isinstance(node.value, ast.BinOp):
                        aliases = self._flatten_nested_tuple(self.visit(node.value))
                        for alias in aliases:
                            all = self.current_token.all_aliases[alias]
                            if all:
                                if self.current_token.all:
                                    self.current_token.all.extend(all)
                                else:
                                    self.current_token.all = all
                            else:
                                self.unresolved_nodes += 1

    def visit_AugAssign(self, node):
        if isinstance(node.target, ast.Name):
            if node.target.id == '__all__':
                if isinstance(node.op, ast.Add) and (isinstance(node.value, ast.Tuple) or isinstance(node.value, ast.List)):
                    if self.current_token.all:
                        self.current_token.all.extend([el.s for el in node.value.elts])
                    else:
                        self.current_token.all = [el.s for el in node.value.elts]
                        self.unresolved_nodes += 1

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Add):  # only parse list concatenation
            return self.visit(node.left), self.visit(node.right)

    def visit_Name(self, node):
        return node.id


class ImportParser(IndeterministicParser):
    """
    Parses import statements of a module, in order to extend the namespace of the corresponding component.
    Stores every imported name with its qualified name in the current_token which imports it.
    Uses the all variable of the current_token, to resolve its wildcard imports.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def visit_ClassDef(self, node):
        self.descend(node)

    def visit_FunctionDef(self, node):
        self.descend(node)

    def visit_Import(self, node):
        for alias in node.names:
            # print("import " + alias.name + " as " + alias.asname)
            if alias.name in self.ns.tokens:
                name = alias.name
                if alias.asname:
                    name = alias.asname
                self.current_token.imported_names[name] = alias.name
            # else:  importing system/external module

    def visit_ImportFrom(self, node):
        from_mod = self._build_qualified_from_name(node)

        for alias in node.names:
            if alias.name == '*':
                if from_mod in self.ns.tokens:
                    from_token = self.ns.tokens[from_mod]
                    if from_token.all is not None:  # from_mod is regular package: import all names from __all__
                        for name in from_token.all:
                            if name in from_token.imported_names:
                                self.current_token.imported_names[name] = from_token.imported_names[name]
                            elif name in from_token.declared_names:
                                self.current_token.imported_names[name] = from_token.declared_names[name]
                            else:
                                self.unresolved_nodes += 1
                    else:  # from_mod is module: import names with no leading underscore
                        for tok in from_token.classes | from_token.functions:
                            if not tok.name.startswith('_'):
                                self.current_token.imported_names[tok.name] = tok.qual_name
                # else:  from_mod excluded in ProjectNamespace
            else:
                name = alias.name
                if alias.asname:
                    name = alias.asname

                qual_name = from_mod + '.' + alias.name
                # print("from " + from_mod + " import " + alias.name)
                if qual_name in self.ns.tokens:  # name is defined in from_mod
                    self.current_token.imported_names[name] = qual_name
                elif from_mod in self.ns.tokens:  # name is imported in from_mod
                    names = self.ns.tokens[from_mod].imported_names
                    if alias.name in names:
                        self.current_token.imported_names[name] = names[name]
                    else:
                        self.unresolved_nodes += 1
                # else:  importing from system/external module or importing local variable/constant


# todo: parse whether attributes are private or not (name.beginswith('_'))
class InstanceAttributeParser(DeterministicParser):
    """
    Parses every assignment to self.<var> and tries to determine its type.
    Only determines basic types through assignment of constants or type casts.
    Resolves instantiation of other classes within the namespace.
    Assignments which assign a variable name or method calls are omitted.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def visit_ClassDef(self, node):
        self.descend(node)

    def visit_FunctionDef(self, node):
        self.descend(node)

    def visit_Assign(self, node):
        for trgt in node.targets:
            if isinstance(trgt, ast.Attribute) and isinstance(trgt.value, ast.Name):
                if trgt.value.id == 'self':
                    dummy_attr = Var(trgt.attr)
                    typ = self.visit(node.value)

                    if typ:
                        # try if typ is class (maybe prefixed)
                        token = self.ns.get_token_of_local_name(self.current_token, typ)
                        if token:
                            self.ns.associations.add(Association(token.gid, self.current_cls.gid, AssocType.AGGREGATE))
                            dummy_attr.type = token.name
                            self.current_cls.inst_attrs.add(dummy_attr)
                        # if typ was not token, filter for constants/type-casts
                        elif typ in ['str', 'int', 'float', 'complex', 'bool', 'bytes', 'null', 'set', 'list', 'tuple', 'dict']:
                            dummy_attr.type = typ
                            self.current_cls.inst_attrs.add(dummy_attr)
                        # else: typ is not imported/declared local name
                    elif dummy_attr not in self.current_cls.inst_attrs:
                        self.current_cls.inst_attrs.add(dummy_attr)
                    # else: node.value is unvisited node

    def visit_Call(self, node):
        name = self.visit(node.func)
        if name:
            return name
        # else: call of unvisited node

    def visit_Attribute(self, node):
        name = self.visit(node.value)
        if name:
            return name + '.' + node.attr
        # else: call of unvisited node

    def visit_Name(self, node):
        return node.id

    def visit_Constant(self, node):
        if type(node.value) is str:
            return 'str'
        elif type(node.value) is int:
            return 'int'
        elif type(node.value) is float:
            return 'float'
        elif type(node.value) is complex:
            return 'complex'
        elif type(node.value) is bool:
            return 'bool'
        elif type(node.value) is bytes:
            return 'bytes'
        elif node.value is None:
            return 'null'

    def visit_List(self, node):
        return 'list'

    def visit_Tuple(self, node):
        return 'tuple'

    def visit_Set(self, node):
        return 'set'

    def visit_Dict(self, node):
        return 'dict'

    def visit_ListComp(self, node):
        return 'list'

    def visit_SetComp(self, node):
        return 'set'

    def visit_DictComp(self, node):
        return 'dict'


class InheritanceParser(DeterministicParser):
    """
    Parses which class inherits from another within the project namespace.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def _make_inheritence(self, node, source_token, base_token):
        dep = Dependency(source_token.gid, base_token.gid, DepenType.REFINES)
        if self._is_abstract_class(node):
            dep.stereotype = Stereotype.REALIZES
        else:
            dep.stereotype = Stereotype.DERIVES
        self.ns.dependencies.add(dep)

    def _is_abstract_class(self, node):
        for base in node.bases:  # python 3.4+
            if isinstance(base, ast.Name):
                if base.id == 'ABC':
                    return True
        for kw in node.keywords:  # python 2.7+
            if kw.arg == 'metaclass' and isinstance(kw.value, ast.Name):
                if kw.value.id == 'ABCMeta':
                    return True

        return False

    def visit_ClassDef(self, node):
        qual_name = self.current_comp.qual_name + '.' + node.name
        if qual_name in self.ns.tokens:
            child = self.ns.tokens[qual_name]
            # parse inheritance/implementation
            for base in node.bases:
                if isinstance(base, ast.Name):
                    name = self.visit(base)
                    # name must be either imported or declared in same module
                    child_qualname = self.current_comp.get_qualname_of_local_name(name)
                    if child_qualname:
                        self._make_inheritence(node, child, self.ns.tokens[child_qualname])
                elif isinstance(base, ast.Attribute):  # prefixed base
                    qual_name = self.visit(base)
                    if qual_name:
                        parent = self.ns.get_token_of_local_name(child, qual_name)
                        if parent:
                            self._make_inheritence(node, child, parent)

    def visit_Attribute(self, node):
        name = self.visit(node.value)
        if name:
            return name + '.' + node.attr
        # else: call of unvisited node

    def visit_Name(self, node):
        return node.id


class CallParser(DeterministicParser):
    """
    Parses the calls of a function to another within the project namespace.
    """
    def __init__(self, ns):
        super().__init__(ns)

    def visit_ClassDef(self, node):
        self.descend(node)

    def visit_FunctionDef(self, node):
        self.descend(node)

    def visit_Call(self, node):
        typ = self.visit(node.func)  # build local qual_name
        if typ:
            trgt_token = self.ns.get_token_of_local_name(self.current_token, typ)
            if trgt_token:
                stereotype = Stereotype.CALLS
                if isinstance(trgt_token, Class):
                    if '__init__' in trgt_token.declared_names:
                        trgt_token = self.ns.tokens[trgt_token.qual_name + '.__init__']
                    else:  # raised error class
                        stereotype = Stereotype.INSTANTIATES

                self.ns.dependencies.add(Dependency(self.current_token.gid, trgt_token.gid, DepenType.USES, stereotype))

    def visit_Attribute(self, node):
        name = self.visit(node.value)
        if name:
            return name + '.' + node.attr
        # else: call of unvisited node

    def visit_Name(self, node):
        return node.id
