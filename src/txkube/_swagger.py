# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
An interface to Swagger specifications.

This module provides the ability to automatically derive somewhat sensible
Python type definitions from definitions in a Swagger specification.  The
Python types enforce the constraints defined by the Swagger specification as
best they can.  They also support being serialized down to raw (JSON-y)
objects and loaded from such objects.
"""

from json import load
from datetime import datetime
from itertools import chain

from dateutil.parser import parse as parse_iso8601

from zope.interface import Attribute, Interface, implementer

from pyrsistent import (
    CheckedValueTypeError, PClass, PVector, pvector, field, pvector_field,
    pmap_field, freeze, pmap,
)

from twisted.python.compat import nativeString
from twisted.python.reflect import fullyQualifiedName


class NotClassLike(Exception):
    """
    An attempt was made to treat a Swagger definition as though it were
    compatible with Python classes but it is not (for example, it is a simple
    type like *string* or *integer*).
    """



class Swagger(PClass):
    """
    A ``Swagger`` contains a single Swagger specification.

    Public attributes of this class correspond to the top-level properties in
    a `Swagger specification <http://swagger.io/>`_.

    :ivar dict _pclasses: A cache of the `PClass`\ es that have been
        constructed for definitions from this specification already.  This
        allows multiple requests for the same definition to be satisfied with
        the same type object (rather than a new type object which has all the
        same attributes and behavior).  This plays better with Python's type
        system than the alternative.
    """
    info = field()
    paths = field()
    definitions = field(factory=freeze)
    securityDefinitions = field()
    security = field()
    swagger = field()

    _pclasses = field(mandatory=True, type=dict)

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


    def pclass_for_definition(self, name, constant_fields=pmap()):
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
            model = generator(name, definition, constant_fields)
            cls = model.pclass()
            self._pclasses[name] = cls
        return cls


    def _identify_kind(self, definition):
        """
        Determine what kind of thing the given definition seems to resemble.

        This must be inferred from the structure of the definition.  For
        example, if it includes the *properties* then the thing is sort of
        like a Python class.

        :param pyrsistent.PMap definition: A Swagger definition to categorize.
            This will be a value like the one found at
            ``spec["definitions"][name]``.

        :return: ``"CLASS"`` for things that are class-like.  ``None``
            otherwise (though it would be good to extend this).
        """
        if u"properties" in definition:
            return "CLASS"
        return None


    def _model_for_CLASS(self, name, definition, constant_fields):
        """
        Model a Swagger definition that is like a Python class.

        :param unicode name: The name of the definition from the
            specification.

        :param pyrsistent.PMap definition: A Swagger definition to categorize.
            This will be a value like the one found at
            ``spec["definitions"][name]``.

        :param dict constant_fields: Additional fields to set as constants on
            the resulting class.  These will override properties from the
            Swagger definition if they collide.
        """
        return _ClassModel.from_swagger(
            self.pclass_for_definition, name, definition,
            constant_fields,
        )



class IRangeModel(Interface):
    """
    An ``IRangeModel`` provider models the range of values a type can take on.
    """
    def pyrsistent_invariant():
        """
        :return: A pyrsistent invariant which enforces the range.  It accepts one
            argument (a value to validate) and returns a two-tuple.  The first
            element is ``True`` if the value is in the range, ``False`` otherwise.
            If it is ``False``, the second element gives a human-readable
            description of how the value fell out of the range.
        """


class ITypeModel(Interface):
    """
    An ``ITypeModel`` provider models the type of a value.

    Such types could be associated with the value of a property or a value
    found in an array or mapping.
    """
    python_types = Attribute("tuple of python types compatible with this type")
    factory = Attribute("An optional callable for converting values to this type.")

    def pclass_field_for_type(required):
        """
        Create a pyrsistent field for this model object for use with a PClass.

        :param bool required: Whether the field should be mandatory or
            optional.

        :return: A pyrsistent field descriptor for an attribute which is
            usable with values of this type.
        """



@implementer(ITypeModel)
class _BasicTypeModel(PClass):
    """
    A ``_BasicTypeModel`` represents a type composed (roughly) of a "single"
    value.

    Specifically, this is used for Swagger types of *boolean*, *integer*,
    *string* (except *date-time*), and references to other *object*\ s.

    :ivar tuple(type) python_types: The Python types which correspond to this
        the modeled Swagger type.

    :ivar IRangeModel range: Optionally, a model of the range of values
        allowed (necessary because, for example, a Python integer type can
        hold arbitrarily large values but the modeled type may be limited to
        the range representable in 32 bits).

    :ivar factory: A one-argument callable which can convert non-canonical
        representations to canonical representations (and which will be
        applied to values provided for use with this type).
    """
    python_types = field(mandatory=True)
    range = field(mandatory=True, initial=None)
    factory = field(mandatory=True, initial=None)
    serializer = field(mandatory=True, initial=lambda: lambda format, value: value)

    def _pyrsistent_invariant(self, required):
        """
        Create a pyrsistent invariant which reflects this model.

        :param bool required: ``True`` if the invariant will require a
            non-``None`` value, ``False`` if ``None`` is allowed in addition
            to whatever ``self.range`` describes.

        :return: A callable suitable for use as a pyrsistent invariant.
        """
        if self.range is None:
            return None
        invariant = self.range.pyrsistent_invariant()
        if required:
            return invariant
        def optional(v):
            if v is None:
                return (True, u"")
            return invariant(v)
        return optional


    def _pyrsistent_factory(self, required):
        """
        Create a pyrsistent field factory which reflects this model.

        :param bool required: ``True`` if the factory will require a
            non-``None`` value, ``False`` if ``None`` is allowed to bypass
            ``self.factory``.

        :return: A callable suitable for use as a pyrsistent factory.
        """
        if self.factory is None:
            return None
        if required:
            return self.factory
        def optional(v):
            if v is None:
                return None
            if isinstance(v, self.python_types):
                return v
            return self.factory(v)
        return optional


    def _pyrsistent_serializer(self, required):
        """
        Create a pyrsistent serialization function.

        :param bool required: ``True`` if this value must appear in the
            serialized form.  ``False`` if it may be omitted when it has a
            ``None`` value.

        :return: A callable suitable for use as a pyrsistent field serializer.
        """
        if required:
            return self.serializer

        def serialize(format, value):
            if value is None:
                return omit
            return self.serializer(format, value)
        return serialize


    def pclass_field_for_type(self, required):
        """
        Construct a pyrsistent field reflecting this model.

        The field uses the model's invariant and factory.  If ``required`` is
        ``False``, an initial value of ``None`` is also supplied.

        :return: The field descriptor.
        """
        extra = {}
        python_types = self.python_types

        invariant = self._pyrsistent_invariant(required)
        if invariant is not None:
            extra[u"invariant"] = invariant

        if not required:
            python_types += (type(None),)
            extra[u"initial"] = None

        factory = self._pyrsistent_factory(required)
        if factory is not None:
            extra[u"factory"] = factory

        extra[u"serializer"] = self._pyrsistent_serializer(required)

        return field(
            mandatory=required, type=python_types, **extra
        )



def provider_invariant(interface):
    """
    :param zope.interface.Interface interface: An interface to require.

    :return: A pyrsistent invariant which requires that values provide the
        given interface.
    """
    return lambda o: (
        interface.providedBy(o),
        "does not provide {}".format(fullyQualifiedName(interface)),
    )



def itypemodel_field():
    """
    :return: A pyrsistent field for an attribute which much refer to an
        ``ITypeModel`` provider.
    """
    return field(invariant=provider_invariant(ITypeModel))



@implementer(ITypeModel)
class _ArrayTypeModel(PClass):
    """
    An ``_ArrayTypeModel`` represents a type which is a homogeneous array.

    Specifically, this is used for the Swagger type *array*.

    :ivar tuple(type) python_types: The Python types which correspond to this
        the modeled Swagger type.

    :ivar ITypeModel element_type: The type model that applies to elements of
        the array.
    """
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



# TODO It might make more sense to handle this the same way as a reference to
# another object.  The current implementation makes it tricky because it's not
# straightforward to name these inline/nested objects (as it is
# straightforward to name a top-level definition).
@implementer(ITypeModel)
class _MappingTypeModel(PClass):
    """
    A ``_MappingTypeModel`` represents a type which is a homogeneous mapping
    with ``unicode`` keys.

    Specifically, this is used for the Swagger type *object* when it occurs
    inline in another definition.

    :ivar ITypeModel value_field: The type model that applies to values in the
        mapping.
    """
    value_type = itypemodel_field()

    def pclass_field_for_type(self, required):
        # XXX ignores the range's pyrsistent_invariant
        return pmap_field(
            key_type=unicode,
            value_type=self.value_type.python_types,
            optional=not required,
        )



class _AttributeModel(PClass):
    """
    An ``_AttributeModel`` models an attribute of a class-like definition.

    Specifically, this is used for an item in a Swagger *object*\ s
    *properties*.

    :ivar unicode name: The name of the attribute.

    :ivar unicode descriptor: The human-meaningful description of the
        attribute.

    :ivar itypemodel_field type_model: The type model for values this
        attribute can reference.

    :ivar bool required: ``True`` if a value conforming to ``type_model`` must
        be supplied.  ``False`` if ``None`` is allowed in addition to values
        allowed by ``type_model``.
    """
    name = field(type=unicode)
    description = field(type=unicode)
    type_model = itypemodel_field()
    required = field(type=bool)

    def pclass_field_for_attribute(self):
        """
        :return: A pyrsistent field reflecting this attribute and its type model.
        """
        return self.type_model.pclass_field_for_type(required=self.required)



class _ConstantModel(PClass):
    """
    A ``_ConstantModel`` models a constant valued attribute.

    This does not correspond to any part of a Swagger specification.  Instead,
    it's part of how a Swagger definition is usefully exposed to Python.  It
    can be used to override certain fields from a Swagger definition (for
    example, when there is a known constant value which the Swagger
    specification can't formally represent).

    :ivar unicode name: The name of the attribute.
    :ivar value: The value of the attribute.
    """
    name = field(type=unicode)
    value = field()

    def pclass_field_for_attribute(self):
        """
        :return: Exactly this model's value, creating a constant-valued attribute
        on a class it is used with.
        """
        return self.value



@implementer(IRangeModel)
class _IntegerRange(PClass):
    """
    ``_IntegerRange`` represents a contiguous range of integer values between
    two boundaries.

    :ivar int min: The lower bound, inclusive.
    :ivar int max: The upper bound, inclusive.
    """
    min = field(type=(int, long))
    max = field(type=(int, long))


    @classmethod
    def from_unsigned_bits(cls, n):
        """
        Create a range corresponding to that of an unsigned integer of ``n``
        bits.
        """
        return cls(min=0, max=2 ** n - 1)

    @classmethod
    def from_signed_bits(cls, n):
        """
        Create a range corresponding to that of a two's complement signed integer
        of ``n`` bits.
        """
        m = n - 1
        return cls(min=-2 ** m, max=2 ** m - 1)


    def pyrsistent_invariant(self):
        """
        :return: An invariant which rejects values outside of *(min, max)*.
        """
        return lambda v: (
            self.min <= v <= self.max,
            "{!r} out of required range ({}, {})".format(v, self.min, self.max),
        )



def _parse_iso8601(text):
    """
    Maybe parse an ISO8601 datetime string into a datetime.

    :param text: Either a ``unicode`` string to parse or any other object
        (ideally a ``datetime`` instance) to pass through.

    :return: A ``datetime.datetime`` representing ``text``.  Or ``text`` if it
        was anything but a ``unicode`` string.
    """
    if isinstance(text, unicode):
        try:
            return parse_iso8601(text)
        except ValueError:
            raise CheckedValueTypeError(
                None, (datetime,), unicode, text,
            )
    # Let pyrsistent reject it down the line.
    return text



def _isoformat(format, v):
    return v.isoformat()



class _ClassModel(PClass):
    """
    A ``_ClassModel`` represents a type with a number of named, heterogeneous
    fields - something like a Python class.

    Specifically, this is used to represent top-level Swagger definitions of
    type *object*.

    :cvar _basic_types: A mapping from the simpler Swagger types to
        ``ITypeModel`` providers which represent them.

    :ivar unicode name: The name of the definition.
    :ivar unicode doc: The description of the definition.
    :ivar PVector attributes: Models for the fields of the definition.
    """
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
        (u"string", u"date-time"): _BasicTypeModel(
            python_types=(datetime,),
            factory=_parse_iso8601,
            serializer=_isoformat,
        ),
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
                return _BasicTypeModel(
                    python_types=(python_type,),
                    factory=python_type.create,
                    serializer=lambda format, value: value.serialize(format),
                )

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
    def from_swagger(cls, pclass_for_definition, name, definition, constant_fields):
        """
        Create a new ``_ClassModel`` from a single Swagger definition.

        :param pclass_for_definition: A callable like
            ``Swagger.pclass_for_definition`` which can be used to resolve
            type references encountered in the definition.

        :param unicode name: The name of the definition.

        :param definition: The Swagger definition to model.  This will be a
            value like the one found at ``spec["definitions"][name]``.

        :param constant_fields: A mapping of properties overrides.

        :return: A new model for the given definition.
        """
        return cls(
            name=name,
            doc=definition.get(u"description", name),
            attributes=chain((
                attr
                for attr
                in cls._attributes_for_definition(pclass_for_definition, definition)
                if constant_fields is None or attr.name not in constant_fields
            ), (
                _ConstantModel(name=name, value=value)
                for (name, value)
                in constant_fields.items()
            )),
        )


    def pclass(self):
        """
        Create a ``pyrsistent.PClass`` subclass representing this class.
        """
        content = {
            attr.name: attr.pclass_field_for_attribute()
            for attr
            in self.attributes
        }
        content["__doc__"] = nativeString(self.doc)
        content["serialize"] = _serialize_with_omit
        return type(nativeString(self.name), (PClass,), content)


omit = object()
def _serialize_with_omit(self, format=None):
    return {
        key: value
        for (key, value)
        in PClass.serialize(self, format).iteritems()
        if value is not omit
    }



class INameTranslator(Interface):
    """
    An ``INameTranslator`` translates from a name convenient for use in Python
    to a name used in a Swagger definition.
    """
    def translate(name):
        """
        Translate the name from Python to Swagger.

        :param unicode name: The Python name.
        :return unicode: The Swagger name.
        """



@implementer(INameTranslator)
class IdentityTranslator(object):
    """
    ``IdentityTranslator`` provides the identity translation.  In other words,
    it is a no-op.
    """
    def translate(self, name):
        return name



@implementer(INameTranslator)
class UsePrefix(PClass):
    """
    ``UsePrefix`` provides a translation which prepends a prefix.  This is
    useful, for example, for a versioning convention where many definition
    names have a prefix like *v1*.

    :ivar unicode prefix: The prefix to prepend.
    """
    prefix = field(mandatory=True, type=unicode)

    def translate(self, name):
        return self.prefix + name



class PClasses(PClass):
    """
    ``PClasses`` provides a somewhat easier to use interface to PClasses
    representing definitions from a Swagger definition.  For example::

    .. code-block: python

       spec = Swagger.from_path(...)
       v1beta1 = PClasses(
           specification=spec,
           name_translator=UsePrefix(u"v1beta1."),
       )
       class Deployment(v1beta1[u"Deployment"]):
           ...
    """
    specification = field(mandatory=True, type=Swagger)
    name_translator = field(
        mandatory=True, initial=IdentityTranslator(),
        invariant=provider_invariant(INameTranslator),
    )

    def __getitem__(self, name):
        """
        Get a PClass for the translation of the given name.

        :param unicode name: The Python name to translate and look up.

        :return: A ``PClass`` subclass for the identified Swagger definition.
        """
        name = self.name_translator.translate(name)
        return self.specification.pclass_for_definition(name)



class VersionedPClasses(object):
    """
    ``VersionedPClasses`` provides a somewhat easier to use interface to
    PClasses representing definitions from a Swagger definition.  For
    example::

    .. code-block: python

       spec = Swagger.from_path(...)
       v1beta1 = VersionedPClasses(
           spec, u"v1beta1", u"kind", u"apiVersion",
       )
       deployment = v1beta1.Deployment(...)
    """
    def __init__(self, spec, version, name_field=None, version_field=None):
        self.spec = spec
        self.version = version
        self.name_field = name_field
        self.version_field = version_field


    def __getattr__(self, name):
        constant_fields = {}
        if self.name_field is not None:
            constant_fields[self.name_field] = name
        if self.version_field is not None:
            constant_fields[self.version_field] = self.version
        definition_name = self.version + u"." + name
        try:
            return self.spec.pclass_for_definition(
                definition_name, constant_fields=constant_fields,
            )
        except KeyError:
            raise AttributeError(name)
