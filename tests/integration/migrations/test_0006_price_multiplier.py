def test_migration_0006_declares_expected_revision_chain():
    """Verify migration 0006 still follows migration 0005."""
    from pathlib import Path
    migration_file = Path("migrations/versions/0006_add_price_multipliers.py")
    assert migration_file.exists(), "Migration file should exist"

    # Verify migration file content
    content = migration_file.read_text()
    assert "revision = '0006'" in content
    assert "down_revision = '0005'" in content
    assert "price_multiplier" in content
    assert "ck_providers_price_multiplier_range" in content
    assert "ck_models_price_multiplier_range" in content


def test_migration_0006_has_correct_structure():
    """Verify migration file has correct structure."""
    from pathlib import Path
    migration_file = Path("migrations/versions/0006_add_price_multipliers.py")
    content = migration_file.read_text()

    # Check upgrade function
    assert "def upgrade() -> None:" in content
    assert "op.add_column" in content
    assert "'providers'" in content
    assert "'models'" in content
    assert "sa.Numeric(4, 2)" in content
    assert "server_default='1.00'" in content

    # Check downgrade function
    assert "def downgrade() -> None:" in content
    assert "op.drop_constraint" in content
    assert "op.drop_column" in content
