from app.catalog import airline_display, airline_label, airline_options


def test_airline_ui_uses_single_brand_name() -> None:
    assert airline_label("Delta") == "Delta"
    assert airline_label("delta air lines") == "Delta"
    assert airline_display("Southwest") == "Southwest"

    options = {option["value"]: option for option in airline_options()}
    assert options["Alaska"]["label"] == "Alaska"
    assert "Alaska Airlines" in options["Alaska"]["keywords"]
