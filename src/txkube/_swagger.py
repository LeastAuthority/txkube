# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An interface to Swagger specifications.
"""

from json import load
from datetime import datetime

from dateutil.parser import parse as parse_iso8601

from zope.interface import Attribute, Interface, implementer

from pyrsistent import (
    CheckedValueTypeError, PClass, PVector, pvector, field, pvector_field,
    pmap_field, freeze,
)

from twisted.python.compat import nativeString


class NotClassLike(Exception):
    pass



class Swagger(PClass):
    """
    A ``Swagger`` contains a single Swagger specification.
    """
    info = field()
    paths = field()
    definitions = field()
    securityDefinitions = field()
    security = field()
    swagger = field()

    _pclasses = field(mandatory=True, factory=dict)


    @classmethod
    def from_path(cls, spec_path):
        """
        Load a specification from a path.

        :param FilePath spec_path: The location of the specification to read.
        """
        with spec_path.open() as spec_file:
            return cls.from_document(load(spec_file))


    @classmethod
    def from_document(cls, document):
        """
        Load a specification from some Python objects.

        :param dict document: An object like the one that might be created by
            parsing a Swagger JSON specification string.
        """
        return cls(_pclasses={}, **document)


    def pclass_for_definition(self, name):
        """
        Get a ``pyrsistent.PClass`` subclass representing the Swagger definition
        in this specification which corresponds to the given name.

        :param unicode name: The name of the definition to use.

        :return: A Python class which can be used to represent the Swagger
            definition of the given name.
        """
        try:
            cls = self._pclasses[name]
        except KeyError:
            definition = self.definitions[name]
            kind = self._identify_kind(definition)
            if kind is None:
                raise NotClassLike(name, definition)
            generator =  getattr(self, "_model_for_{}".format(kind))
            model = generator(name, definition)
            cls = model.pclass()
            self._pclasses[name] = cls
        return cls


    def _identify_kind(self, definition):
        if u"properties" in definition:
            return "CLASS"
        return None


    def _model_for_CLASS(self, name, definition):
        """
        Model a Swagger definition that is like a Python class.
        """
        return _ClassModel.from_swagger(self.pclass_for_definition, name, definition)



class ITypeModel(Interface):
    python_types = Attribute("tuple of python types compatible with this type")
    factory = Attribute("An optional callable for converting values to this type.")

    def pclass_field_for_type(required):
        """
        Create a pyrsistent field for this model object for use with a PClass.
        """



@implementer(ITypeModel)
class _BasicTypeModel(PClass):
    python_types = field(mandatory=True)
    range = field(mandatory=True, initial=None)
    factory = field(mandatory=True, initial=None)

    def pclass_field_for_type(self, required):
        extra = {}
        python_types = self.python_types
        if self.range is not None:
            # XXX Allow None here
            extra[u"invariant"] = self.range.pyrsistent_invariant()
        if not required:
            python_types += (type(None),)
            extra[u"initial"] = None
        if self.factory is not None:
            extra[u"factory"] = self.factory
        return field(
            mandatory=required, type=python_types, **extra
        )



@implementer(ITypeModel)
class _DatetimeTypeModel(object):
    python_types = datetime

    def _parse(self, value):
        if isinstance(value, self.python_types):
            return value
        if isinstance(value, unicode):
            try:
                return parse_iso8601(value)
            except ValueError:
                raise CheckedValueTypeError(
                    None, self.python_types, unicode, value,
                )
        # Let pyrsistent reject it.
        return value


    def pclass_field_for_type(self, required):
        return field(
            mandatory=required, type=self.python_types,
            factory=self._parse,
            serializer=lambda d: d.isoformat(),
        )


def itypemodel_field():
    return field(
        invariant=lambda o: (
            ITypeModel.providedBy(o),
            "does not provide ITypeModel",
        ),
    )



@implementer(ITypeModel)
class _ArrayTypeModel(PClass):
    element_type = itypemodel_field()

    @property
    def python_types(self):
        # Cheat a bit and make pyrsistent synthesize a type for us...
        # Amusingly, it's a regular set internally so also freeze it so it's
        # okay to put it back in to field again.
        return freeze(self.pclass_field_for_type(True).type)

    def pclass_field_for_type(self, required):
        # XXX ignores the range's pyrsistent_invariant
        return pvector_field(self.element_type.python_types, optional=not required)



@implementer(ITypeModel)
class _MappingTypeModel(PClass):
    value_type = itypemodel_field()

    def pclass_field_for_type(self, required):
        # XXX ignores the range's pyrsistent_invariant
        return pmap_field(
            key_type=unicode,
            value_type=self.value_type.python_types,
            optional=not required,
        )


class _AttributeModel(PClass):
    name = field(type=unicode)
    description = field(type=unicode)
    type_model = field(invariant=lambda o: (ITypeModel.providedBy(o), "does not provide ITypeModel"))
    required = field(type=bool)

    def pclass_field_for_attribute(self):
        return self.type_model.pclass_field_for_type(required=self.required)



class _IntegerRange(PClass):
    min = field(type=(int, long))
    max = field(type=(int, long))

    @classmethod
    def from_unsigned_bits(cls, n):
        return cls(min=0, max=2 ** n - 1)

    @classmethod
    def from_signed_bits(cls, n):
        m = n - 1
        return cls(min=-2 ** m, max=2 ** m - 1)

    def pyrsistent_invariant(self):
        return lambda v: (
            self.min <= v <= self.max,
            "{!r} out of required range ({}, {})".format(v, self.min, self.max),
        )



class _ClassModel(PClass):
    _basic_types = {
        (u"boolean", None): _BasicTypeModel(python_types=(bool,)),
        (u"integer", u"int32"): _BasicTypeModel(
            # XXX Kubernetes uses this to mean unsigned 32 bit integer.
            # Swagger spec says it is for signed 32 bit integer.  Since we're
            # trying to *use* Kubernetes ...
            python_types=(int, long), range=_IntegerRange.from_unsigned_bits(32),
        ),
        (u"integer", u"int64"): _BasicTypeModel(
            python_types=(int, long), range=_IntegerRange.from_unsigned_bits(64),
        ),
        (u"string", None): _BasicTypeModel(python_types=(unicode,)),
        (u"string", u"byte"): _BasicTypeModel(python_types=(bytes,)),
        (u"string", u"date-time"): _DatetimeTypeModel(),
        (u"string", u"int-or-string"): _BasicTypeModel(
            python_types=(unicode, int, long),
        ),
    }

    name = field(type=unicode)
    doc = field(type=unicode)
    attributes = field(type=PVector, factory=pvector)

    @classmethod
    def _type_model_for_spec(cls, pclass_for_definition, spec):
        if spec.get(u"type") == u"array":
            # "array" type definitions represent an array of some other thing.
            # Get a model for whatever the nested thing is and put it into an
            # array model.
            element_type = cls._type_model_for_spec(
                pclass_for_definition, spec[u"items"],
            )
            return _ArrayTypeModel(element_type=element_type)

        if spec.get(u"type") == u"object":
            # "object" type definitions represent a mapping from unicode to
            # some other thing.  Get a model for whatever the values are
            # supposed to be and put that into a mapping model.
            value_type = cls._type_model_for_spec(
                pclass_for_definition, spec[u"additionalProperties"],
            )
            return _MappingTypeModel(value_type=value_type)

        if u"$ref" in spec:
            # "$ref" type definitions refer to some other definition in the
            # specification.  Look that up and use it.
            name = spec[u"$ref"]
            assert name.startswith(u"#/definitions/")
            name = name[len(u"#/definitions/"):]
            try:
                # For anything that's class-like (basically, has properties)
                # we'll get another PClass for the reference target.
                python_type = pclass_for_definition(name)
            except NotClassLike as e:
                # For anything that's not class-like (it could be a simple
                # type like a string), create a simple type model for it instead.
                #
                # The spec is conveniently available in the exception
                # arguments.  This is an awful way to pass information around.
                # Probably some refactoring is in order.
                _, spec = e.args
                return cls._type_model_for_spec(
                    pclass_for_definition, spec,
                )
            else:
                # For our purposes, the pclass we got is just another basic
                # type we can model.
                return _BasicTypeModel(python_types=(python_type,), factory=python_type.create)

        # If it wasn't any of those kinds of things, maybe it's just a simple
        # type.  Look up the corresponding model object in the static mapping.
        return cls._basic_types[spec[u"type"], spec.get(u"format", None)]


    @classmethod
    def _attribute_for_property(
        cls, pclass_for_definition, name, required, definition
    ):
        type_model = cls._type_model_for_spec(pclass_for_definition, definition)
        return _AttributeModel(name=name, required=required, type_model=type_model)


    @classmethod
    def _attributes_for_definition(cls, pclass_for_definition, definition):
        required = definition.get(u"required", [])
        for prop, spec in definition[u"properties"].items():
            yield cls._attribute_for_property(
                pclass_for_definition, prop, prop in required, spec,
            )


    @classmethod
    def from_swagger(cls, pclass_for_definition, name, definition):
        return cls(
            name=name,
            doc=definition.get(u"description", name),
            attributes=cls._attributes_for_definition(pclass_for_definition, definition),
        )


    def pclass(self):
        """
        Create a PClass representing this class.
        """
        content = {
            attr.name: attr.pclass_field_for_attribute()
            for attr
            in self.attributes
        }
        content["__doc__"] = nativeString(self.doc)
        return type(nativeString(self.name), (PClass,), content)
