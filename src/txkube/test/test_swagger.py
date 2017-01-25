# Copyright Least Authority Enterprises.
# See LICENSE for details.

"""
Tests for ``txkube._swagger``.
"""

from pyrsistent import InvariantException, CheckedValueTypeError, PTypeError, PClass

from twisted.python.filepath import FilePath

from testtools.matchers import (
    Equals, MatchesPredicate, MatchesStructure, Raises,
    IsInstance, MatchesAll, AfterPreprocessing,
)

from .._swagger import Swagger

from ..testing import TestCase


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


def raises_exception(cls, **attributes):
    def get_exception((type, exception, traceback)):
        return exception
    return Raises(
        AfterPreprocessing(
            get_exception,
            MatchesAll(
                IsInstance(cls),
                MatchesStructure(**{
                    k: Equals(v) for (k, v) in attributes.items()
                }),
                first_only=True,
            ),
        ),
    )
