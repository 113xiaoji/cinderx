import unittest


class CompatPolicyTests(unittest.TestCase):
    def test_oss_support_family_is_only_314(self) -> None:
        from cinderx import _compat

        self.assertEqual(_compat.OSS_SUPPORTED_MINOR_FAMILIES, ("3.14", "3.15"))

    def test_314_validated_patches_are_explicit(self) -> None:
        from cinderx import _compat

        family = _compat.get_family_policy("3.14")
        self.assertIsNotNone(family)
        assert family is not None
        self.assertEqual(
            family.validated_patches,
            ("3.14.0", "3.14.1", "3.14.2", "3.14.3"),
        )
        self.assertEqual(family.default_build_patch, "3.14.3")
        self.assertTrue(family.publish_wheels)
        self.assertEqual(
            family.arm64_enabled_features,
            frozenset({"adaptive_static_python", "lightweight_frames"}),
        )

    def test_unknown_minor_family_is_not_supported(self) -> None:
        from cinderx import _compat

        self.assertIsNone(_compat.get_family_policy("3.16"))

    def test_315_validated_patch_and_defaults_are_explicit(self) -> None:
        from cinderx import _compat

        family = _compat.get_family_policy("3.15")
        self.assertIsNotNone(family)
        assert family is not None
        self.assertEqual(family.validated_patches, ("3.15.0a6+",))
        self.assertEqual(family.default_build_patch, "3.15.0a6+")
        self.assertTrue(family.publish_wheels)
        self.assertEqual(family.arm64_enabled_features, frozenset())

    def test_oss_feature_defaults_are_policy_driven(self) -> None:
        from cinderx import _compat

        self.assertTrue(
            _compat.is_oss_feature_enabled("3.14", "arm64", "adaptive_static_python")
        )
        self.assertTrue(
            _compat.is_oss_feature_enabled("3.14", "aarch64", "lightweight_frames")
        )
        self.assertFalse(
            _compat.is_oss_feature_enabled("3.14", "x86_64", "adaptive_static_python")
        )
        self.assertFalse(
            _compat.is_oss_feature_enabled("3.15", "arm64", "lightweight_frames")
        )


if __name__ == "__main__":
    unittest.main()
