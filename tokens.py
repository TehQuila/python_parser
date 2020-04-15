from enum import Enum
from abc import abstractmethod


class NameSpace:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.declared_names = {}  # names defined within namespace, <local name, qualified_name>
        self.imported_names = {}  # reverse lookup table <local name, qualified_name>

    def get_qualname_of_local_name(self, name):
        if name in self.declared_names:
            return self.declared_names[name]
        elif name in self.imported_names:
            return self.imported_names[name]
        else:
            return None


class Token:
    def __init__(self, gid, qual_name, **kwargs):
        super().__init__(**kwargs)
        self.gid = gid
        self.name = qual_name.split('.')[-1]
        self.qual_name = qual_name

    def __hash__(self):
        return hash(self.qual_name)

    def __eq__(self, other):
        return self.qual_name == other.qual_name

    @abstractmethod
    def to_dict(self):
        raise NotImplementedError


class Package(Token):
    def __init__(self, gid, qual_name, **kwargs):
        super().__init__(gid=gid, qual_name=qual_name)

        self.packages = set()
        self.components = set()

        self.relations = set()

    def to_dict(self):
        return dict(
            id=self.gid, name=self.name, qual_name=self.qual_name,
            relations=[r.to_dict() for r in self.relations],
            packages=[p.to_dict() for p in self.packages],
            components=[m.to_dict() for m in self.components],
        )


class Component(Package, NameSpace):
    def __init__(self, gid, qual_name):
        super().__init__(gid=gid, qual_name=qual_name)
        self.regular_pkg = False  # regular package is a folder-module
        self.all = None  # names which are imported on wildcard import
        self.all_aliases = {}  # lookup <alias, imported all>
        self.classes = set()
        self.functions = set()

    def to_dict(self):
        return dict(
            id=self.gid, name=self.name, qual_name=self.qual_name,
            all=self.all, declared_names=self.declared_names, imported_names=self.imported_names,
            relations=[r.to_dict() for r in self.relations],
            packages=[p.to_dict() for p in self.packages],
            components=[m.to_dict() for m in self.components],
            classes=[c.to_dict() for c in self.classes],
            functions=[f.to_dict() for f in self.functions],
        )


class Denominator(Enum):
    ABSTRACT = 'abstract'
    INTERFACE = 'interface'


class Class(Token, NameSpace):
    def __init__(self, gid, qual_name):
        super().__init__(gid=gid, qual_name=qual_name)

        self.inst_attrs = set()
        self.inst_methods = set()
        self.relations = set()

    def to_dict(self):
        return dict(
            id=self.gid, name=self.name, qual_name=self.qual_name, imported_names=self.imported_names,
            relations=[r.to_dict() for r in self.relations],
            inst_attrs=[a.to_dict() for a in self.inst_attrs],
            inst_meths=[m.to_dict() for m in self.inst_methods],
        )


class Function(Token, NameSpace):
    def __init__(self, gid, qual_name, params=None):
        super().__init__(gid=gid, qual_name=qual_name)

        self.params = []
        for param in params:
            self.params.append(Var(param))

    def to_dict(self):
        return dict(
            id=self.gid, name=self.name, imported_names=self.imported_names,
            params=[p.to_dict() for p in self.params],
        )


class Var:
    def __init__(self, name, typ=""):
        self.name = name
        self.type = typ

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def to_dict(self):
        return dict(name=self.name, type=self.type)


class Relation:
    def __init__(self, src_id, tgt_id, rel_type, weight=0):
        self.src_id = src_id
        self.tgt_id = tgt_id
        self.weight = weight
        self.type = rel_type

    def __eq__(self, other):
        return self.src_id == other.src_id and self.tgt_id == other.tgt_id and self.weight == other.weight

    def __hash__(self):
        return hash(str(self.src_id) + str(self.tgt_id) + str(self.weight))

    def to_dict(self):
        return dict(source=self.src_id, target=self.tgt_id, weight=self.weight, type=self.type.value)


class AssocType(Enum):
    AGGREGATE = 'aggregation'
    COMPOSE = 'composition'


class DepenType(Enum):
    USES = 'uses'
    REFINES = 'refines'


class Stereotype(Enum):
    CALLS = 'calls'
    INSTANTIATES = 'instantiates'
    DERIVES = 'derives'
    REALIZES = 'realizes'


class Dependency(Relation):
    def __init__(self, src_id, tgt_id, depen_type, stereotype=None, weight=0):
        super().__init__(src_id, tgt_id, depen_type, weight)
        self.stereotype = stereotype

    def to_dict(self):
        d = dict(source=self.src_id, target=self.tgt_id, weight=self.weight, type=self.type.value)
        if self.stereotype:
            d['stereotype'] = self.stereotype.value

        return d


class Association(Relation):
    def __init__(self, src_id, tgt_id, assoc_type=None, weight=0):
        super().__init__(src_id, tgt_id, assoc_type, weight)

