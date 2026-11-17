import unittest

from organ_21_configuration_schema import (
    SchemaCore, ConfigKeyDefinition, DataType, Environment,
    DependencyRule, DependencyCondition, MigrationRule, MigrationAction,
    ErrorCode, SchemaException, CompatibilityStatus,
)


def core_with_keys() -> SchemaCore:
    core = SchemaCore()
    core.register_key(ConfigKeyDefinition(
        config_id="1", config_path="kernel.process.max_threads",
        key_name="max_threads", description="Max worker threads",
        category="KERNEL", data_type=DataType.INTEGER, required=True,
        default_value=4, minimum_value=1, maximum_value=256))
    core.register_key(ConfigKeyDefinition(
        config_id="2", config_path="brain.llm.context_window",
        key_name="context_window", description="LLM context window",
        category="BRAIN", data_type=DataType.INTEGER, required=False,
        default_value=8192, minimum_value=1024, maximum_value=131072))
    core.register_key(ConfigKeyDefinition(
        config_id="3", config_path="brain.llm.use_local",
        key_name="use_local", description="Use local LLM runtime",
        category="BRAIN", data_type=DataType.BOOLEAN, required=False,
        default_value=True, mutually_exclusive_with=("brain.llm.use_remote",)))
    core.register_key(ConfigKeyDefinition(
        config_id="4", config_path="brain.llm.use_remote",
        key_name="use_remote", description="Use remote LLM API",
        category="BRAIN", data_type=DataType.BOOLEAN, required=False,
        default_value=False, mutually_exclusive_with=("brain.llm.use_local",)))
    core.register_key(ConfigKeyDefinition(
        config_id="5", config_path="kernel.memory.max_heap",
        key_name="max_heap", description="Max heap memory",
        category="KERNEL", data_type=DataType.MEMORY_SIZE, required=False,
        default_value=536870912))
    return core


class TypeParsingTests(unittest.TestCase):
    def test_duration_parsing(self):
        core = core_with_keys()
        self.assertEqual(core.type_manager.parse("2h", DataType.DURATION, "x"), 7_200_000)

    def test_memory_parsing(self):
        core = core_with_keys()
        self.assertEqual(core.type_manager.parse("512MB", DataType.MEMORY_SIZE, "x"), 536870912)

    def test_percentage_bounds(self):
        core = core_with_keys()
        self.assertAlmostEqual(core.type_manager.parse("85%", DataType.CPU_PERCENTAGE, "x"), 0.85)
        with self.assertRaises(SchemaException):
            core.type_manager.parse("150%", DataType.CPU_PERCENTAGE, "x")


class RegistrationTests(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        core = core_with_keys()
        with self.assertRaises(SchemaException):
            core.register_key(ConfigKeyDefinition(
                config_id="1b", config_path="kernel.process.max_threads",
                key_name="dup", description="dup", category="KERNEL",
                data_type=DataType.INTEGER))


class ValidationTests(unittest.TestCase):
    def test_valid_payload_passes(self):
        core = core_with_keys()
        result = core.validate_configuration(
            "KERNEL", {"kernel.process.max_threads": 8}, Environment.PRODUCTION)
        self.assertTrue(result.valid)
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(result.validated_payload["kernel.process.max_threads"], 8)

    def test_undocumented_key_rejected(self):
        core = core_with_keys()
        result = core.validate_configuration(
            "KERNEL", {"kernel.process.unknown_key": 1}, Environment.PRODUCTION)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, ErrorCode.ERR_UNDOCUMENTED_KEY)

    def test_constraint_exceeded(self):
        core = core_with_keys()
        result = core.validate_configuration(
            "KERNEL", {"kernel.process.max_threads": 999}, Environment.PRODUCTION)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, ErrorCode.ERR_CONSTRAINT_EXCEEDED)

    def test_mutual_exclusivity(self):
        core = core_with_keys()
        result = core.validate_configuration(
            "BRAIN", {"brain.llm.use_local": True, "brain.llm.use_remote": True},
            Environment.PRODUCTION)
        self.assertFalse(result.valid)
        codes = {e.code for e in result.errors}
        self.assertIn(ErrorCode.ERR_MUTUAL_EXCLUSIVITY_VIOLATION, codes)

    def test_missing_required_uses_default(self):
        core = core_with_keys()
        result = core.validate_configuration("KERNEL", {}, Environment.PRODUCTION)
        self.assertTrue(result.valid)
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(result.validated_payload["kernel.process.max_threads"], 4)


class DependencyTests(unittest.TestCase):
    def test_dependency_requires_target(self):
        core = core_with_keys()
        core.register_key(ConfigKeyDefinition(
            config_id="6", config_path="cloud.api.key",
            key_name="api_key", description="Cloud API key",
            category="CLOUD", data_type=DataType.STRING, required=False,
            dependencies=(DependencyRule("cloud.enabled", DependencyCondition.EXISTS),)))
        result = core.validate_configuration(
            "CLOUD", {"cloud.api.key": "abc"}, Environment.PRODUCTION)
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, ErrorCode.ERR_DEPENDENCY_UNSATISFIED)


class VersionCompatibilityTests(unittest.TestCase):
    def test_same_major_compatible(self):
        core = core_with_keys()
        self.assertEqual(core.check_compatibility("1.2.0"), CompatibilityStatus.COMPATIBLE)

    def test_next_major_requires_migration(self):
        core = core_with_keys()
        self.assertEqual(core.check_compatibility("2.0.0"), CompatibilityStatus.MIGRATION_REQUIRED)

    def test_far_major_incompatible(self):
        core = core_with_keys()
        self.assertEqual(core.check_compatibility("5.0.0"), CompatibilityStatus.INCOMPATIBLE)


class MigrationTests(unittest.TestCase):
    def test_rename_migration(self):
        core = SchemaCore()
        core.register_key(ConfigKeyDefinition(
            config_id="7", config_path="old.path", key_name="old",
            description="legacy key", category="LEGACY", data_type=DataType.STRING,
            migration_rules=(MigrationRule("1.0.0", "2.0.0", MigrationAction.RENAME,
                                            rename_to="new.path"),)))
        migrated = core.migrate_configuration({"old.path": "value"}, "1.0.0", "2.0.0")
        self.assertEqual(migrated["new.path"], "value")
        self.assertNotIn("old.path", migrated)


class AuditTests(unittest.TestCase):
    def test_audit_signature_verifies(self):
        core = core_with_keys()
        record = core.audit_manager.log_event("TEST_EVENT", "some.path")
        self.assertTrue(core.audit_manager.verify(record))


if __name__ == "__main__":
    unittest.main()
