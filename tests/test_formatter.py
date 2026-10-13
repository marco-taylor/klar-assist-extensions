import unittest
from .fixture_files import files
from .helpers import UNITS, rows
from custom_components.klar_assist_extensions.modules.weather import formatter as f


class FormatterTests(unittest.TestCase):
    def test_cloud_boundaries(self):
        for value, expected in [(0,'klar'), (10,'klar'), (11,'leicht bewölkt'), (30,'leicht bewölkt'),
                (31,'teilweise bewölkt'), (60,'teilweise bewölkt'), (61,'stark bewölkt'), (85,'stark bewölkt'),
                (86,'bedeckt'), (100,'bedeckt')]:
            with self.subTest(value=value):
                self.assertEqual(f.cloud_description(value), expected)
        for value in [None,-1,101,float('nan'),True]:
            self.assertIsNone(f.cloud_description(value))

    def test_wind_boundaries(self):
        for value, expected in [(0,'windstill'), (1.99,'windstill'), (2,'leichter Wind'), (11.99,'leichter Wind'),
                (12,'schwacher Wind'), (19.99,'schwacher Wind'), (20,'mäßiger Wind'), (28.99,'mäßiger Wind'),
                (29,'frischer Wind'), (38.99,'frischer Wind'), (39,'starker Wind'), (49.99,'starker Wind'),
                (50,'stürmischer Wind'), (61.99,'stürmischer Wind'), (62,'Sturm'), (74,'Sturm'), (74.01,'schwerer Sturm')]:
            with self.subTest(value=value):
                self.assertEqual(f.wind_description(value), expected)

    def test_units(self):
        for unit, value in [('km/h',20), ('m/s',20/3.6), ('mph',20/1.609344), ('kn',20/1.852)]:
            self.assertAlmostEqual(f.wind_kmh(value,unit),20)
        self.assertIsNone(f.wind_kmh(20,'unknown'))
        self.assertIsNone(f.wind_sentence({'wind_speed':20},{'wind_speed_unit':'unknown'}))
        self.assertEqual(f.temperature(32,{'temperature_unit':'°F'}),0)
        self.assertEqual(f.precipitation(1,{'precipitation_unit':'in'}),25.4)

    def test_storm_gusts(self):
        answer = f.wind_sentence({'wind_speed':65,'wind_gust_speed':90},UNITS)
        self.assertIn('Sturm',answer)
        self.assertIn('65 Kilometer pro Stunde',answer)
        self.assertIn('Böen erreichen etwa 90',answer)
        self.assertEqual(f.wind_sentence({'wind_speed':20,'wind_gust_speed':50},UNITS), 'Es weht ein mäßiger Wind.')

    def test_zero_and_missing_values(self):
        answer = f.format_weather({'temperature':0,'templow':0,'precipitation':0,
                 'precipitation_probability':0,'humidity':0,'cloud_coverage':0,'wind_speed':0},UNITS,'Heute')
        for expected in ['zwischen 0 und 0 Grad','0 Prozent','0 Millimeter','klar','windstill']:
            self.assertIn(expected,answer)
        self.assertEqual(f.format_weather({},UNITS,'Heute'),'Es liegen gerade keine Wetterwerte vor.')

    def test_phase_one_and_compact_formatter_identical(self):
        original = {}
        exec(compile(files['tests/fixtures/legacy_formatter.py'],'legacy_formatter','exec'),original)
        for row in rows()+[{}, {'temperature':0,'templow':0,'precipitation':0},
                          {'temperature':None,'humidity':None,'wind_speed':65,'wind_gust_speed':90}]:
            for current in [False,True]:
                for rain in [False,True]:
                    self.assertEqual(f.format_weather(row,UNITS,'Morgen',current=current,rain_only=rain),
                                     original['format_weather'](row,UNITS,'Morgen',current=current,rain_only=rain))
            self.assertEqual(f.compact_day(row,UNITS,'Mittwoch'),original['compact_day'](row,UNITS,'Mittwoch'))

    def test_non_finite_numbers_omitted(self):
        for value in [True,False,float('inf'),float('nan'),None,'oops']:
            self.assertIsNone(f.number(value))

    def test_current_does_not_invent_minimum(self):
        answer=f.format_weather({'temperature':10,'templow':2},UNITS,'Aktuell',current=True)
        self.assertNotIn('2 Grad',answer)
        self.assertNotIn('zwischen',answer)
