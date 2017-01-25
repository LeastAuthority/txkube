# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An interface to Swagger specifications.
"""

from json import load

from zope.interface import Attribute, Interface, implementer

from pyrsistent import PClass, PVector, pvector, field, pvector_field

from twisted.python.compat import nativeString


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
            generator =  getattr(self, "_model_for_{}".format(kind))
            model = generator(name, definition)
            cls = model.pclass()
            self._pclasses[name] = cls
        return cls


    def _identify_kind(self, definition):
        if u"properties" in definition:
            return "CLASS"
        raise Exception("Unsupported stuff", definition)


    def _model_for_CLASS(self, name, definition):
        """
        Model a Swagger definition that is like a Python class.
        """
        return _ClassModel.from_swagger(self.pclass_for_definition, name, definition)



class ITypeModel(Interface):
    python_types = Attribute("tuple of python types compatible with this type")

    def pclass_field_for_type(required):
        """
        Create a pyrsistent field for this model object for use with a PClass.
        """



@implementer(ITypeModel)
class _BasicTypeModel(PClass):
    python_types = field(mandatory=True)
    range = field(mandatory=True, initial=None)

    def pclass_field_for_type(self, required):
        if self.range is None:
            extra = {}
        else:
            extra = dict(invariant=self.range.pyrsistent_invariant())
        return field(
            mandatory=required, type=self.python_types, **extra
        )



    def pclass_field_for_type(self, required):
        return field(mandatory=required, type=self.python_types)



@implementer(ITypeModel)
class _ArrayTypeModel(PClass):
    element_type = field(invariant=lambda o: (ITypeModel.providedBy(o), "does not provide ITypeModel"))

    def pclass_field_for_type(self, required):
        # XXX ignores the range's pyrsistent_invariant
        return pvector_field(self.element_type.python_types, optional=not required)



class _AttributeModel(PClass):
    name = field(type=unicode)
    description = field(type=unicode)
    type_model = field(invariant=lambda o: (ITypeModel.providedBy(o), "does not provide ITypeModel"))
    required = field(type=bool)

    def pclass_field_for_attribute(self):
        return self.type_model.pclass_field_for_type(required=self.required)



class _IntegerRange(PClass):
    min = field(type=int)
    max = field(type=int)

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
            "out of required range ({}, {})".format(self.min, self.max),
        )



class _ClassModel(PClass):
    _basic_types = {
        (u"integer", u"int32"): _BasicTypeModel(
            # XXX Kubernetes uses this to mean unsigned 32 bit integer.
            # Swagger spec says it is for signed 32 bit integer.  Since we're
            # trying to *use* Kubernetes ...
            python_types=(int, long), range=_IntegerRange.from_unsigned_bits(32),
        ),
        (u"string", None): _BasicTypeModel(python_types=(unicode,)),
        (u"string", u"byte"): _BasicTypeModel(python_types=(bytes,)),
    }

    name = field(type=unicode)
    doc = field(type=unicode)
    attributes = field(type=PVector, factory=pvector)

    @classmethod
    def _type_model_for_spec(cls, pclass_for_definition, spec):
        if spec.get(u"type") == u"array":
            element_type = cls._type_model_for_spec(
                pclass_for_definition, spec[u"items"],
            )
            return _ArrayTypeModel(element_type=element_type)

        if u"$ref" in spec:
            name = spec[u"$ref"]
            assert name.startswith(u"#/definitions/")
            name = name[len(u"#/definitions/"):]
            pclass = pclass_for_definition(name)
            return _BasicTypeModel(python_types=(pclass,))

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
            doc=definition[u"description"],
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
