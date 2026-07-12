from app.models.sub_region import SubRegion, SubRegionFeature


def test_sub_region_has_lake_cell_year_identity_and_embedding():
    columns = SubRegion.__table__.c

    assert {"sub_region_id", "lake_id", "cell_number", "year", "embedding"} <= set(columns.keys())
    assert "uq_sub_region_lake_cell_year" in {
        constraint.name for constraint in SubRegion.__table__.constraints
    }


def test_sub_region_features_belong_to_a_sub_region():
    columns = SubRegionFeature.__table__.c

    assert "sub_region_id" in columns
    assert "uq_sub_region_feature_year" in {
        constraint.name for constraint in SubRegionFeature.__table__.constraints
    }
