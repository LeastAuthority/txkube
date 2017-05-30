# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._swagger``.
"""

from datetime import datetime

from hypothesis import given
from hypothesis.strategies import sampled_from, integers

from eliot import Message

from pyrsistent import (
    InvariantException, CheckedKeyTypeError, CheckedValueTypeError,
    PTypeError, PClass, freeze,
)

from twisted.python.filepath import FilePath

from testtools.matchers import (
    Equals, MatchesPredicate,
    IsInstance, MatchesAll, Is, raises,
)

from .._swagger import (
    NotClassLike, NoSuchDefinition, AlreadyCreatedClass,
    Swagger, _IntegerRange,
    UsePrefix, PClasses, VersionedPClasses,
)

from ..testing import TestCase
from ..testing.matchers import raises_exception


def swagger_primitive_types():
    """
    Hypothesis strategy to build Swagger *primitive* type definitions.
    """
    def _swaggered((t, f)):
        result = {u"type": t}
        if f is not None:
            result[u"format"] = f
        return result

    return sampled_from([
        (u"integer", u"int32"),
        (u"integer", u"int64"),
        (u"string", None),
        (u"string", u"byte"),
        (u"string", u"date-time"),
        (u"boolean", None),
    ]).map(_swaggered)



class _IntegerRangeTests(TestCase):
    """
    Tests for ``_IntegerRange``.
    """
    def test_from_signed_bits(self):
        """
        ``_IntegerRange.from_signed_bits`` returns an ``_IntegerRange`` with lower
        and upper bounds set to the smallest and largest values a signed
        integer of the given width can represent.
        """
        r = _IntegerRange.from_signed_bits(4)
        self.assertThat(r, Equals(_IntegerRange(min=-8, max=7)))


    def test_from_unsigned_bits(self):
        """
        ``_IntegerRange.from_unsigned_bits`` returns an ``_IntegerRange`` with
        lower and upper bounds set to the smallest and largest values an
        unsigned integer of the given width can represent.
        """
        r = _IntegerRange.from_unsigned_bits(4)
        self.assertThat(r, Equals(_IntegerRange(min=0, max=15)))



class SwaggerTests(TestCase):
    spec_document = {
        u"definitions": {
            u"simple-type": {
                u"type": u"string",
            },
            u"optional-description": {
                u"properties": {
                },
            },
            u"boolean": {
                u"description": u"has type boolean",
                u"properties": {
                    u"v": {
                        u"description": u"",
                        u"type": u"boolean"
                    },
                }
            },
            u"required-boolean": {
                u"description": u"has type boolean",
                u"required": [
                    u"v",
                ],
                u"properties": {
                    u"v": {
                        u"description": u"required property",
                        u"type": u"boolean"
                    },
                }
            },
            u"string.unlabeled": {
                u"description": u"has type string and no format",
                u"properties": {
                    u"s": {
                        u"description": u"",
                        u"type": u"string"
                    },
                }
            },
            u"integer.int32": {
                u"description": u"has type integer and format int32",
                u"properties": {
                    u"i": {
                        u"description": u"",
                        u"type": u"integer",
                        u"format": u"int32"
                    },
                },
            },
            u"integer.int64": {
                u"description": u"has type integer and format int64",
                u"properties": {
                    u"i": {
                        u"description": u"",
                        u"type": u"integer",
                        u"format": u"int64"
                    },
                },
            },
            u"string.date-time": {
                u"description": u"has type string and format date-time",
                u"properties": {
                    u"s": {
                        u"description": u"",
                        u"type": u"string",
                        u"format": u"date-time",
                    },
                },
            },
            u"string.int-or-string": {
                u"description": u"has type string and format int-or-string",
                u"properties": {
                    u"s": {
                        u"description": u"",
                        u"type": u"string",
                        u"format": u"int-or-string",
                    },
                },
            },
            u"object": {
                u"description": u"has type object",
                u"properties": {
                    u"o": {
                        u"type": u"object",
                        u"additionalProperties": {
                            u"type": u"string",
                        },
                    },
                },
            },
            u"object-with-simple-ref": {
                u"description": u"has type object and $ref with simple type target",
                u"properties": {
                    u"p": {
                        u"$ref": u"#/definitions/simple-type",
                    },
                },
            },
            u"object-with-complex-ref": {
                u"description": u"has type object and $ref with type target of another class",
                u"properties": {
                    u"p": {
                        u"$ref": u"#/definitions/object-with-simple-ref",
                    },
                },
            },
            u"object-with-array": {
                u"description": u"has type object and array values",
                u"properties": {
                    u"o": {
                        u"type": u"object",
                        u"additionalProperties": {
                            u"type": u"array",
                            u"items": {
                                u"type": u"string",
                            },
                        },
                    },
                },
            },
            u"object-with-property-with-default": {
                u"description": u"has property with a default value",
                u"properties": {
                    u"d": {
                        u"type": u"string",
                        u"default": u"success",
                    },
                },
            },
        },
    }

    def setUp(self):
        super(SwaggerTests, self).setUp()
        self.spec = Swagger.from_document(self.spec_document)


    def test_hashing(self):
        self.assertThat(
            hash(self.spec),
            IsInstance(int),
        )


    def test_simple_type(self):
        self.assertThat(
            lambda: self.spec.pclass_for_definition(u"simple-type"),
            raises_exception(
                NotClassLike,
                args=(u"simple-type", {u"type": u"string"}),
            ),
        )


    def test_optional_description(self):
        Type = self.spec.pclass_for_definition(u"optional-description")
        self.assertThat(Type(), IsInstance(Type))


    @given(swagger_primitive_types())
    def test_nonrequired_none_default(self, swagger_type):
        spec = Swagger.from_document({
            u"definitions": {
                u"object": {
                    u"properties": {
                        u"o": swagger_type,
                    },
                },
            },
        })
        Type = spec.pclass_for_definition(u"object")
        self.expectThat(Type().o, Is(None))
        self.expectThat(Type().serialize(), Equals({}))


    def test_boolean(self):
        Type = self.spec.pclass_for_definition(u"boolean")
        self.expectThat(
            lambda: Type(v=3),
            raises_exception(PTypeError),
        )
        self.expectThat(
            lambda: Type(v=u"true"),
            raises_exception(PTypeError),
        )
        self.expectThat(Type(v=True).v, Equals(True))
        self.expectThat(Type(v=False).v, Equals(False))
        self.expectThat(Type(v=True).serialize(), Equals({u"v": True}))
        self.expectThat(Type(v=False).serialize(), Equals({u"v": False}))


    def test_required_default_serializer(self):
        Type = self.spec.pclass_for_definition(u"required-boolean")
        self.expectThat(Type(v=True).serialize(), Equals({u"v": True}))


    def test_integer_int32_errors(self):
        Type = self.spec.pclass_for_definition(u"integer.int32")
        self.expectThat(
            lambda: Type(i=u"foo"),
            raises_exception(PTypeError),
        )
        self.expectThat(
            lambda: Type(i=2 ** 32),
            raises_exception(InvariantException),
        )
        self.expectThat(
            lambda: Type(i=-1),
            raises_exception(InvariantException),
        )


    @given(integers(min_value=0, max_value=2 ** 32 - 1))
    def test_integer_int32_valid(self, expected):
        Type = self.spec.pclass_for_definition(u"integer.int32")
        self.assertThat(
            Type(i=expected).i,
            Equals(expected),
        )
        # The property is not required so we can set it to None.
        self.expectThat(Type(i=None).i, Is(None))
        # The property is not required so it defaults to None.
        self.expectThat(Type().i, Is(None))


    def test_integer_int64_errors(self):
        Type = self.spec.pclass_for_definition(u"integer.int64")
        self.expectThat(
            lambda: Type(i=u"foo"),
            raises_exception(PTypeError),
        )
        self.expectThat(
            lambda: Type(i=2 ** 64),
            raises_exception(InvariantException),
        )
        self.expectThat(
            lambda: Type(i=-1),
            raises_exception(InvariantException),
        )


    @given(integers(min_value=0, max_value=2 ** 64 - 1))
    def test_integer_int64_valid(self, expected):
        Type = self.spec.pclass_for_definition(u"integer.int64")
        self.assertThat(
            Type(i=expected).i,
            Equals(expected),
        )


    def test_string_unlabeled(self):
        Type = self.spec.pclass_for_definition(u"string.unlabeled")
        self.expectThat(
            lambda: Type(s=b"foo"),
            raises_exception(PTypeError),
        )
        self.expectThat(Type(s=u"bar").s, Equals(u"bar"))


    def test_string_date_time(self):
        Type = self.spec.pclass_for_definition(u"string.date-time")
        self.expectThat(
            lambda: Type(s=b"foo"),
            raises_exception(PTypeError),
        )
        self.expectThat(
            lambda: Type(s=u"foo"),
            raises_exception(CheckedValueTypeError),
        )
        now = datetime.utcnow()
        self.expectThat(Type(s=now).s, Equals(now))
        self.expectThat(Type(s=now.isoformat().decode("ascii")).s, Equals(now))

        # string / date-time fields serialize back to an ISO8601 format
        # string.
        serialized = Type(s=now).serialize()
        self.expectThat(
            serialized,
            Equals({u"s": now.isoformat().decode("ascii")}),
        )
        # Thanks for making bytes and unicode compare equal, Python.
        self.expectThat(serialized[u"s"], IsInstance(unicode))
        # Missing values don't appear in the output.
        self.expectThat(
            Type(s=None).serialize(),
            Equals({}),
        )
        self.expectThat(
            Type().serialize(),
            Equals({}),
        )


    def test_string_int_or_string(self):
        Type = self.spec.pclass_for_definition(u"string.int-or-string")
        self.expectThat(
            lambda: Type(s=b"foo"),
            raises_exception(PTypeError),
        )
        self.expectThat(Type(s=u"foo").s, Equals(u"foo"))
        self.expectThat(Type(s=u"50").s, Equals(u"50"))
        self.expectThat(Type(s=50).s, Equals(50))
        self.expectThat(Type(s=50L).s, Equals(50))


    def test_object(self):
        Type = self.spec.pclass_for_definition(u"object")
        self.expectThat(
            lambda: Type(o=3),
            raises_exception(AttributeError),
        )
        self.expectThat(
            lambda: Type(o={b"foo": u"bar"}),
            raises_exception(CheckedKeyTypeError),
        )
        self.expectThat(
            lambda: Type(o={u"foo": b"bar"}),
            raises_exception(CheckedValueTypeError),
        )
        self.expectThat(
            Type(o={u"foo": u"bar"}).o,
            Equals({u"foo": u"bar"}),
        )


    def test_property_ref_simple(self):
        Type = self.spec.pclass_for_definition(u"object-with-simple-ref")
        self.expectThat(
            lambda: Type(p=3),
            raises_exception(PTypeError),
        )
        self.expectThat(Type(p=u"foo").p, Equals(u"foo"))


    def test_property_ref_complex(self):
        Simple = self.spec.pclass_for_definition(u"object-with-simple-ref")
        Complex = self.spec.pclass_for_definition(u"object-with-complex-ref")
        self.expectThat(
            Complex(p=Simple(p=u"foo")).p,
            Equals(Simple(p=u"foo")),
        )
        # Allow construction with a dictionary that maps properly onto the
        # target type, too.
        self.expectThat(
            Complex(p={u"p": u"foo"}).p,
            Equals(Simple(p=u"foo")),
        )
        # It is not marked as required so we can set it to None.
        self.expectThat(Complex(p=None).p, Is(None))
        # It should also default to None.
        self.expectThat(Complex().p, Is(None))
        # Serialization is recursive.
        self.expectThat(
            Complex(p=Simple(p=u"foo")).serialize(),
            Equals({u"p": {u"p": u"foo"}}),
        )


    def test_property_object_arrays(self):
        Type = self.spec.pclass_for_definition(u"object-with-array")
        self.assertThat(
            Type(o={u"foo": [u"bar"]}).o,
            Equals({u"foo": [u"bar"]}),
        )


    def test_property_with_default(self):
        Type = self.spec.pclass_for_definition(
            u"object-with-property-with-default"
        )
        self.expectThat(Type().d, Equals(u"success"))
        self.expectThat(Type(d=u"x").d, Equals(u"x"))


    def test_transform_definition(self):
        """
        A definition can be altered arbitrarily by supplying a value for
        ``transform_definition``.
        """
        spec = self.spec.set(
            u"transform_definition",
            lambda n, d: d.transform(
                [u"properties", u"invented"],
                {u"type": u"boolean"},
            ),
        )
        Type = spec.pclass_for_definition(u"boolean")
        self.assertThat(Type(invented=False).invented, Equals(False))



class Kubernetes15SwaggerTests(TestCase):
    """
    An integration test for the Swagger generator against the Kubernetes 1.5
    specification.
    """
    spec_path = FilePath(__file__).parent().sibling(b"kubernetes-1.5.json")

    def test_loading(self):
        """
        The specification can be loaded from a file.
        """
        Swagger.from_path(self.spec_path)


    def test_everything(self):
        """
        Load every single definition from the specification.

        This is a smoke test.  If it breaks, write some more specific tests
        and then fix the problem.
        """
        spec = Swagger.from_path(self.spec_path)
        for name in sorted(spec.definitions):
            Message.log(name=name)
            try:
                spec.pclass_for_definition(name)
            except NotClassLike:
                # Some stuff, indeed, is not ...
                pass


    def test_properties_required_definition(self):
        """
        ``Swagger.pclass_for_definition`` returns a ``PClass`` representing the
        Swagger definition identified by its argument.
        """
        spec = Swagger.from_path(self.spec_path)
        # Arbitrarily select a very simple definition from the spec.  It
        # demonstrates handling of "description", "properties", "required".
        name = u"runtime.RawExtension"
        RawExtension = spec.pclass_for_definition(name)
        self.expectThat(RawExtension, is_subclass(PClass))
        self.expectThat(
            RawExtension.__doc__,
            Equals(spec.definitions[name][u"description"]),
        )

        self.expectThat(
            lambda: RawExtension(),
            raises_exception(
                InvariantException,
                invariant_errors=(),
                missing_fields=("runtime.RawExtension.Raw",),
                args=("Field invariant failed",),
            ),
        )

        self.expectThat(
            lambda: RawExtension(Raw=object()),
            raises_exception(
                PTypeError,
                source_class=RawExtension,
                field="Raw",
                expected_types={bytes},
                actual_type=object,
            ),
        )

        self.expectThat(
            lambda: RawExtension(Raw=u"foo"),
            raises_exception(
                PTypeError,
                source_class=RawExtension,
                field="Raw",
                expected_types={bytes},
                actual_type=unicode,
            ),
        )
        self.expectThat(
            lambda: RawExtension(Raw=b"foo", raw=b"foo").Raw,
            raises_exception(AttributeError),
        )
        self.expectThat(RawExtension(Raw=b"foo").Raw, Equals(b"foo"))


    def test_array_property(self):
        """
        For a definition with a property of type *array*,
        ``Swagger.pclass_for_definition`` returns a ``PClass`` with a
        corresponding field which requires a ``PVector`` of some type.
        """
        spec = Swagger.from_path(self.spec_path)
        # Arbitrarily select a simple definition that includes an array from
        # the spec.  It also demonstrates that "required" itself is optional.
        name = u"v1.Capabilities"
        Capabilities = spec.pclass_for_definition(name)

        self.expectThat(
            lambda: Capabilities(add=b"hello"),
            raises_exception(
                CheckedValueTypeError,
                expected_types=(unicode,),
                actual_type=bytes,
            ),
        )


    def test_reference_property(self):
        """
        For a definition with a property with a ``$ref`` reference,
        ``Swagger.pclass_for_definition`` returns a ``PClass`` with a
        corresponding field values for which must be instances of another
        ``PClass`` derived from the target of that reference.
        """
        spec = Swagger.from_path(self.spec_path)
        # Arbitrarily select a simple definition that includes an array from
        # the spec.  It also demonstrates that "required" itself is optional.
        name = u"v1.APIGroup"
        APIGroup = spec.pclass_for_definition(name)
        GroupVersionForDiscovery = spec.pclass_for_definition(u"v1.GroupVersionForDiscovery")
        self.assertThat(
            lambda: APIGroup(
                name=u"group",
                versions=[spec],
            ),
            raises_exception(
                TypeError,
            ),
        )

        group_version = GroupVersionForDiscovery(
            groupVersion=u"group/version",
            version=u"version",
        )

        self.assertThat(
            APIGroup(name=u"group", versions=[group_version]).versions,
            Equals([group_version]),
        )



def is_subclass(cls):
    return MatchesPredicate(
        lambda value: issubclass(value, cls),
        "%%s is not a subclass of %s" % (cls,),
    )


class PClassesTests(TestCase):
    """
    Tests for ``PClasses``.
    """
    def test_useprefix(self):
        """
        ``PClasses`` can be used with ``UsePrefix`` to get access to the
        ``PClass``\ s representing Swagger definitions without repetition of
        the definition version prefix commonly used.
        """
        template = freeze({
            u"type": u"object",
            u"properties": {},
        })
        spec = Swagger.from_document({
            u"definitions": {
                u"a.X": template,
                u"b.X": template,
            },
        })
        pclasses = PClasses(
            specification=spec,
            name_translator=UsePrefix(prefix=u"a."),
        )
        self.assertThat(
            pclasses[u"X"], Is(spec.pclass_for_definition(u"a.X")),
        )


    def test_no_definition(self):
        """
        If there is no definition matching the requested name,
        ``PClasses.__getitem__`` raises ``KeyError``.
        """
        pclasses = PClasses(specification=Swagger.from_document({
            u"definitions": {},
        }))
        self.assertThat(
            lambda: pclasses[u"Foo"],
            raises(NoSuchDefinition(u"Foo")),
        )


    def test_default_translator(self):
        """
        If no name translator is provided, ``PClasses`` looks up a definition
        exactly matching the name passed to ``PClasses.__getitem__``.
        """
        spec = Swagger.from_document({
            u"definitions": {
                u"foo": {
                    u"type": u"object",
                    u"properties": {},
                },
            },
        })
        pclasses = PClasses(specification=spec)
        self.assertThat(
            pclasses[u"foo"],
            Is(spec.pclass_for_definition(u"foo")),
        )



class VersionedPClassesTests(TestCase):
    """
    Tests for ``VersionedPClasses``.
    """
    def setUp(self):
        super(VersionedPClassesTests, self).setUp()
        self.spec = Swagger.from_document({
            u"definitions": {
                u"a.foo": {
                    u"type": u"object",
                    u"properties": {
                        u"kind": {
                            u"description": u"",
                            u"type": u"string"
                        },
                        u"apiVersion": {
                            u"description": u"",
                            u"type": u"string"
                        },
                        u"x": {
                            u"description": u"",
                            u"type": u"string"
                        },
                    },
                },
                u"a.foolist": {
                    u"type": u"object",
                    u"properties": {
                        u"items": {
                            u"type": u"array",
                            u"items": {
                                u"$ref": u"#/definitions/a.foo",
                            },
                        },
                    },
                },
                u"k8s.StatusDetails": {
                    u"type": u"object",
                    u"properties": {
                        u"kind": {
                            u"type": u"string",
                        },
                    },
                },
            },
        })
        self.spec = VersionedPClasses.transform_definitions(self.spec)


    def test_attribute_access(self):
        """
        Accessing an attribute of a ``VersionedPClasses`` instance gets a
        ``PClass`` subclass for a Swagger definition matching the
        ``VersionedPClasses`` version and the name of the attribute.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        self.assertThat(
            a.foo,
            Is(self.spec.pclass_for_definition(u"a.foo")),
        )


    def test_kind(self):
        """
        An attribute of the class retrieved from ``VersionedPClasses`` named by
        the value given in the call to ``transform_definitions`` exposes the
        **kind** the type corresponds to.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        self.assertThat(
            a.foo.kind,
            MatchesAll(IsInstance(unicode), Equals(u"foo")),
        )


    def test_version(self):
        """
        An attribute of the class retrieved from ``VersionedPClasses`` named by
        the value given in the call to ``transform_definitions`` exposes the
        **apiVersion** the type corresponds to.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        # Aaahh.  Direct vs indirect first access can make a difference. :(
        a.foolist
        self.assertThat(
            a.foo.apiVersion,
            MatchesAll(IsInstance(unicode), Equals(u"a")),
        )


    def test_missing(self):
        """
        An attribute access on ``VersionedPClasses`` for which there is no
        corresponding Swagger definition results in ``AttributeError`` being
        raised.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        self.assertThat(lambda: a.bar, raises(AttributeError("bar")))


    def test_add_behavior_for_class(self):
        """
        A Python class can be mixed in to the hierarchy of the class returned by
        ``VersionedPClasses`` attribute access using the class decorator
        ``add_behavior_for_pclass``.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        def add_behavior(a):
            @a.add_behavior_for_pclass
            class foo(object):
                def __invariant__(self):
                    return [(self.x, "__invariant__!")]

                def bar(self):
                    return u"baz"
        add_behavior(a)

        an_a = a.foo(x=u"foo")
        self.expectThat(an_a.apiVersion, Equals(u"a"))
        self.expectThat(an_a.kind, Equals(u"foo"))
        self.expectThat(an_a.bar(), Equals(u"baz"))

        self.expectThat(
            lambda: a.foo(x=u""),
            raises_exception(InvariantException),
        )

        # It's not allowed now that we've retrieved the foo class.
        self.expectThat(
            lambda: add_behavior(a),
            raises_exception(AlreadyCreatedClass),
        )

        # It's not allowed for a class that doesn't match a known definition.
        self.expectThat(
            # There is no b.foo so this will try to use an unknown definition.
            lambda: add_behavior(VersionedPClasses(self.spec, {u"b"})),
            raises_exception(NoSuchDefinition),
        )


    def test_irrelevant_constructor_values(self):
        """
        Values may be passed to the Python class constructor for the kind and
        apiVersion and they are discarded.
        """
        a = VersionedPClasses(self.spec, {u"a"})
        self.expectThat(
            a.foo(apiVersion=u"a", kind=u"foo", x=u"x").x,
            Equals(u"x"),
        )


    def test_relevant_constructor_values(self):
        """
        Definitions which do not correspond to Kubernetes Objects do not have
        **kind** discarded.
        """
        k8s = VersionedPClasses(self.spec, {u"k8s"})
        self.assertThat(
            k8s.StatusDetails(kind=u"foo").kind,
            Equals(u"foo"),
        )
