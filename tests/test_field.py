import pytest

from django.core.serializers import deserialize, serialize
from django.db import transaction
from django.db.models import Field, Model
from django.test import TestCase

import json
import warnings
from decimal import Decimal
from pint import DimensionalityError, UndefinedUnitError, UnitRegistry
from typing import Type, Union

from quantityfield.fields import (
    BigIntegerQuantityField,
    DecimalQuantityField,
    IntegerQuantityField,
    QuantityField,
    QuantityFieldMixin,
)
from quantityfield.units import ureg
from tests.dummyapp.models import (
    CustomUregDecimalHayBale,
    CustomUregHayBale,
    EmptyHayBaleBigInt,
    EmptyHayBaleDecimal,
    EmptyHayBaleFloat,
    EmptyHayBaleInt,
    HayBale,
)

Quantity = ureg.Quantity


class BaseMixinTestFieldCreate:
    # The field that needs to be tested
    FIELD: Type[Union[Field, QuantityFieldMixin]]
    # Some fields, i.e. the decimal require default kwargs to work properly
    DEFAULT_KWARGS = {}

    def test_sets_units(self):
        test_grams = self.FIELD("gram", **self.DEFAULT_KWARGS)
        self.assertEqual(test_grams.units, ureg.gram)

    def test_fails_with_unknown_units(self):
        with self.assertRaises(UndefinedUnitError):
            test_crazy_units = self.FIELD(  # noqa: F841
                "zinghie", **self.DEFAULT_KWARGS
            )

    def test_base_units_is_required(self):
        with self.assertRaises(TypeError):
            no_units = self.FIELD(**self.DEFAULT_KWARGS)  # noqa: F841

    def test_base_units_set_with_name(self):
        okay_units = self.FIELD(base_units="meter", **self.DEFAULT_KWARGS)  # noqa: F841

    def test_base_units_are_invalid(self):
        with self.assertRaises(ValueError):
            wrong_units = self.FIELD(None, **self.DEFAULT_KWARGS)  # noqa: F841

    def test_unit_choices_must_be_valid_units(self):
        with self.assertRaises(UndefinedUnitError):
            self.FIELD(base_units="mile", unit_choices=["gunzu"], **self.DEFAULT_KWARGS)

    def test_unit_choices_must_match_base_dimensionality(self):
        with self.assertRaises(DimensionalityError):
            self.FIELD(
                base_units="gram",
                unit_choices=["meter", "ounces"],
                **self.DEFAULT_KWARGS
            )


class TestFloatFieldCrate(BaseMixinTestFieldCreate, TestCase):
    FIELD = QuantityField


class TestIntegerFieldCreate(BaseMixinTestFieldCreate, TestCase):
    FIELD = IntegerQuantityField


class TestBigIntegerFieldCreate(BaseMixinTestFieldCreate, TestCase):
    FIELD = BigIntegerQuantityField


class TestDecimalFieldCreate(BaseMixinTestFieldCreate, TestCase):
    FIELD = DecimalQuantityField
    DEFAULT_KWARGS = {"max_digits": 10, "decimal_places": 2}


@pytest.mark.parametrize(
    "max_digits, decimal_places, error",
    [
        (None, None, "Invalid initialization.*expect.*integers.*"),
        (10, None, "Invalid initialization.*expect.*integers.*"),
        (None, 2, "Invalid initialization.*expect.*integers.*"),
        (-1, 2, "Invalid initialization.*positive.*larger than decimal_places.*"),
        (2, -1, "Invalid initialization.*positive.*larger than decimal_places.*"),
        (2, 3, "Invalid initialization.*positive.*larger than decimal_places.*"),
    ],
)
def test_decimal_init_fail(max_digits, decimal_places, error):
    with pytest.raises(ValueError, match=error):
        DecimalQuantityField(
            "meter", max_digits=max_digits, decimal_places=decimal_places
        )


@pytest.mark.parametrize("max_digits, decimal_places", [(2, 0), (2, 2), (1, 0)])
def decimal_init_success(max_digits, decimal_places):
    DecimalQuantityField("meter", max_digits=max_digits, decimal_places=decimal_places)


@pytest.mark.django_db
class TestCustomDecimalUreg(TestCase):
    def setUp(self):
        # Custom Values are fined in confest.py
        CustomUregDecimalHayBale.objects.create(custom_decimal=Decimal("5"))
        CustomUregDecimalHayBale.objects.create(
            custom_decimal=Decimal("5") * ureg.kilocustom,
        )

    def tearDown(self):
        CustomUregHayBale.objects.all().delete()

    def test_custom_ureg_decimal(self):
        obj = CustomUregDecimalHayBale.objects.first()
        self.assertEqual(str(obj.custom_decimal), "5.00 custom")

        obj = CustomUregDecimalHayBale.objects.last()
        self.assertEqual(str(obj.custom_decimal), "5000.00 custom")


@pytest.mark.django_db
class TestCustomUreg(TestCase):
    def setUp(self):
        # Custom Values are fined in confest.py
        CustomUregHayBale.objects.create(custom=5, custom_int=5, custom_bigint=5)
        CustomUregHayBale.objects.create(
            custom=5 * ureg.kilocustom,
            custom_int=5 * ureg.kilocustom,
            custom_bigint=5 * ureg.kilocustom,
        )

    def tearDown(self):
        CustomUregHayBale.objects.all().delete()

    def test_custom_ureg_float(self):
        obj = CustomUregHayBale.objects.first()
        self.assertIsInstance(obj.custom, ureg.Quantity)
        self.assertEqual(str(obj.custom), "5.0 custom")

        obj = CustomUregHayBale.objects.last()
        self.assertEqual(str(obj.custom), "5000.0 custom")

    def test_custom_ureg_int(self):
        obj = CustomUregHayBale.objects.first()
        self.assertIsInstance(obj.custom_int, ureg.Quantity)
        self.assertEqual(str(obj.custom_int), "5 custom")

        obj = CustomUregHayBale.objects.last()
        self.assertEqual(str(obj.custom_int), "5000 custom")

    def test_custom_ureg_bigint(self):
        obj = CustomUregHayBale.objects.first()
        self.assertIsInstance(obj.custom_int, ureg.Quantity)
        self.assertEqual(str(obj.custom_bigint), "5 custom")

        obj = CustomUregHayBale.objects.last()
        self.assertEqual(str(obj.custom_bigint), "5000 custom")


class BaseMixinNullAble:
    EMPTY_MODEL: Type[Model]
    FLOAT_SET_STR = "707.7"
    FLOAT_SET = float(FLOAT_SET_STR)
    DB_FLOAT_VALUE_EXPECTED = 707.7

    def setUp(self):
        self.EMPTY_MODEL.objects.create(name="Empty")

    def tearDown(self) -> None:
        self.EMPTY_MODEL.objects.all().delete()

    def test_accepts_assigned_null(self):
        new = self.EMPTY_MODEL()
        new.weight = None
        new.name = "Test"
        new.save()
        self.assertIsNone(new.weight)
        # Also get it from database to verify
        from_db = self.EMPTY_MODEL.objects.last()
        self.assertIsNone(from_db.weight)

    def test_accepts_auto_null(self):
        empty = self.EMPTY_MODEL.objects.first()
        self.assertIsNone(empty.weight, None)

    def test_accepts_default_pint_unit(self):
        new = self.EMPTY_MODEL(name="DefaultPintUnitTest")
        units = UnitRegistry()
        new.weight = 5 * units.kilogram
        # Different Registers so we expect a warning!
        with self.assertWarns(RuntimeWarning):
            new.save()
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "DefaultPintUnitTest")
        self.assertEqual(obj.weight.units, "gram")
        self.assertEqual(obj.weight.magnitude, 5000)

    def test_accepts_default_app_unit(self):
        new = self.EMPTY_MODEL(name="DefaultAppUnitTest")
        new.weight = 5 * ureg.kilogram
        # Make sure that the correct argument does not raise a warning
        with warnings.catch_warnings(record=True) as w:
            new.save()
        assert len(w) == 0
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "DefaultAppUnitTest")
        self.assertEqual(obj.weight.units, "gram")
        self.assertEqual(obj.weight.magnitude, 5000)

    def test_accepts_assigned_whole_number(self):
        new = self.EMPTY_MODEL(name="WholeNumber")
        new.weight = 707
        new.save()
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "WholeNumber")
        self.assertEqual(obj.weight.units, "gram")
        self.assertEqual(obj.weight.magnitude, 707)

    def test_accepts_assigned_float_number(self):
        new = self.EMPTY_MODEL(name="FloatNumber")
        new.weight = self.FLOAT_SET
        new.save()
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "FloatNumber")
        self.assertEqual(obj.weight.units, "gram")
        # We expect the database to deliver the correct type, at least
        # for postgresql this is true
        self.assertEqual(obj.weight.magnitude, self.DB_FLOAT_VALUE_EXPECTED)
        self.assertIsInstance(obj.weight.magnitude, type(self.DB_FLOAT_VALUE_EXPECTED))

    def test_serialisation(self):
        serialized = serialize(
            "json",
            [
                self.EMPTY_MODEL.objects.first(),
            ],
        )
        deserialized = json.loads(serialized)
        obj = deserialized[0]["fields"]
        self.assertEqual(obj["name"], "Empty")
        self.assertIsNone(obj["weight"])
        obj_generator = deserialize("json", serialized, ignorenonexistent=True)
        obj_back = next(obj_generator)
        self.assertEqual(obj_back.object.name, "Empty")
        self.assertIsNone(obj_back.object.weight)


@pytest.mark.django_db
class TestNullableFloat(BaseMixinNullAble, TestCase):
    EMPTY_MODEL = EmptyHayBaleFloat


@pytest.mark.django_db
class TestNullableInt(BaseMixinNullAble, TestCase):
    EMPTY_MODEL = EmptyHayBaleInt
    DB_FLOAT_VALUE_EXPECTED = round(BaseMixinNullAble.FLOAT_SET)


@pytest.mark.django_db
class TestNullableBigInt(BaseMixinNullAble, TestCase):
    EMPTY_MODEL = EmptyHayBaleBigInt
    DB_FLOAT_VALUE_EXPECTED = round(BaseMixinNullAble.FLOAT_SET)


@pytest.mark.django_db
class TestNullableDecimal(BaseMixinNullAble, TestCase):
    EMPTY_MODEL = EmptyHayBaleDecimal
    DB_FLOAT_VALUE_EXPECTED = Decimal(BaseMixinNullAble.FLOAT_SET_STR)

    def test_with_default_implementation(self):
        new = self.EMPTY_MODEL(name="FloatNumber")
        new.weight = self.FLOAT_SET
        new.compare = self.FLOAT_SET
        new.save()
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "FloatNumber")
        self.assertEqual(obj.weight.units, "gram")
        # We compare with the reference implementation of django, this should
        # be always true no matter which database is used
        self.assertEqual(obj.weight.magnitude, obj.compare)
        self.assertIsInstance(obj.weight.magnitude, type(obj.compare))

    def test_with_decimal(self):
        new = self.EMPTY_MODEL(name="FloatNumber")
        new.weight = Decimal(self.FLOAT_SET_STR)
        new.compare = Decimal(self.FLOAT_SET_STR)
        new.save()
        obj = self.EMPTY_MODEL.objects.last()
        self.assertEqual(obj.name, "FloatNumber")
        self.assertEqual(obj.weight.units, "gram")
        # We compare with the reference implementation of django, this should
        # be always true no matter which database is used
        self.assertEqual(obj.weight.magnitude, obj.compare)
        self.assertIsInstance(obj.weight.magnitude, type(obj.compare))
        # But we also expect (at least for postgresql) that this a Decimal
        self.assertEqual(obj.weight.magnitude, self.DB_FLOAT_VALUE_EXPECTED)
        self.assertIsInstance(obj.weight.magnitude, Decimal)


@pytest.mark.django_db
class TestFieldSave(TestCase):
    def setUp(self):
        HayBale.objects.create(
            weight=100,
            weight_int=100,
            weight_bigint=100,
            weight_decimal=100,
            name="grams",
        )
        HayBale.objects.create(weight=Quantity(10 * ureg.ounce), name="ounce")
        self.lightest = HayBale.objects.create(weight=1, name="lightest")
        self.heaviest = HayBale.objects.create(weight=1000, name="heaviest")

    def tearDown(self):
        HayBale.objects.all().delete()

    def test_stores_value_in_base_units(self):
        item = HayBale.objects.get(name="ounce")
        self.assertEqual(item.weight.units, "gram")
        self.assertAlmostEqual(item.weight.magnitude, 283.49523125)

    def test_store_integer_loss_of_precision(self):
        with transaction.atomic():
            with self.assertRaisesRegex(ValueError, "loss of precision"):
                HayBale(name="x", weight=0, weight_int=Quantity(10 * ureg.ounce)).save()
        with transaction.atomic():
            with self.assertRaisesRegex(ValueError, "loss of precision"):
                HayBale(
                    name="x", weight=0, weight_bigint=Quantity(10 * ureg.ounce)
                ).save()

    def test_fails_with_incompatible_units(self):
        # we have to wrap this in a transaction
        # fixing a unit test problem
        # http://stackoverflow.com/questions/21458387/transactionmanagementerror-you-cant-execute-queries-until-the-end-of-the-atom
        metres = Quantity(100 * ureg.meter)
        with transaction.atomic():
            with self.assertRaises(DimensionalityError):
                HayBale.objects.create(weight=metres, name="Should Fail")

    def test_value_stored_as_quantity(self):
        obj = HayBale.objects.first()
        self.assertIsInstance(obj.weight, Quantity)
        self.assertEqual(str(obj.weight), "100.0 gram")
        self.assertEqual(str(obj.weight_int), "100 gram")
        self.assertEqual(str(obj.weight_bigint), "100 gram")

    def test_value_stored_as_correct_magnitude_type(self):
        obj = HayBale.objects.first()
        self.assertIsInstance(obj.weight, Quantity)
        self.assertIsInstance(obj.weight.magnitude, float)
        self.assertIsInstance(obj.weight_int.magnitude, int)
        self.assertIsInstance(obj.weight_bigint.magnitude, int)

    def test_value_conversion(self):
        obj = HayBale.objects.first()
        ounces = obj.weight.to(ureg.ounce)
        self.assertAlmostEqual(ounces.magnitude, 3.52739619496)
        self.assertEqual(ounces.units, ureg.ounce)

    def test_order_by(self):
        qs = HayBale.objects.all().order_by("weight")
        self.assertEqual(qs[0].name, "lightest")

    def test_comparison_with_number(self):
        qs = HayBale.objects.filter(weight__gt=2)
        self.assertNotIn(self.lightest, qs)

    def test_comparison_with_quantity(self):
        weight = Quantity(20 * ureg.gram)
        qs = HayBale.objects.filter(weight__gt=weight)
        self.assertNotIn(self.lightest, qs)

    def test_comparison_with_quantity_respects_units(self):
        # 1 ounce = 28.34 grams
        weight = Quantity(0.8 * ureg.ounce)
        qs = HayBale.objects.filter(weight__gt=weight)
        self.assertNotIn(self.lightest, qs)

    def test_comparison_is_actually_numeric(self):
        qs = HayBale.objects.filter(weight__gt=1.0)
        self.assertNotIn(self.lightest, qs)

    def test_serialisation(self):
        serialized = serialize(
            "json",
            [
                HayBale.objects.first(),
            ],
        )
        deserialized = json.loads(serialized)
        obj = deserialized[0]["fields"]
        self.assertEqual(obj["weight"], "100.0")
        self.assertEqual(obj["weight_int"], "100")
