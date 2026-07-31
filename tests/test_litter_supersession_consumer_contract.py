import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
READ_SERVICE = ROOT / "modules/pig_weights/farm_supabase_read_service.py"


class LitterSupersessionConsumerContractTests(unittest.TestCase):
    def test_later_table_migrations_refresh_supersession_guards(self):
        migration_dir = ROOT / "supabase" / "migrations"
        rail_name = "202607300001_create_litter_supersession_rail.sql"
        for path in migration_dir.glob("*.sql"):
            if path.name <= rail_name:
                continue
            source = path.read_text(encoding="utf-8").lower()
            if "create table" in source:
                self.assertIn(
                    "refresh_litter_supersession_write_guards",
                    source,
                    f"{path.name} creates a table without refreshing guards",
                )

    def test_current_eligibility_services_do_not_resolve_from_base_pigs(self):
        paths = [
            "modules/pig_weights/purpose_correction_batch_service.py",
            "modules/sales/riversdale_auction_list.py",
            "modules/sales/sales_transaction_lifecycle.py",
        ]
        for relative in paths:
            source = (ROOT / relative).read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "from public.pigs", source,
                f"{relative} must resolve current eligibility canonically",
            )
        observation = (
            ROOT / "modules/pig_weights/herdmaster_breeding_observation_service.py"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("public.current_canonical_pigs", observation)
        self.assertIn("exists (", observation)

    def test_canonical_farm_reader_uses_current_views(self):
        source = READ_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("from public.litters", source)
        self.assertNotIn("public.pig_current_state", source)
        self.assertGreaterEqual(
            source.count("public.current_canonical_litters"), 3
        )
        self.assertGreaterEqual(
            source.count("public.current_canonical_pig_state"), 7
        )

    def test_write_services_keep_base_identity_targets(self):
        source = (
            ROOT / "modules/pig_weights/farm_supabase_write_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("insert into public.litters", source)
        self.assertIn("insert into public.pigs", source)
        self.assertNotIn("litter_supersessions", source)

    def test_no_module_uses_unfiltered_current_state_view(self):
        offenders = []
        for path in (ROOT / "modules").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "public.pig_current_state" in source:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
