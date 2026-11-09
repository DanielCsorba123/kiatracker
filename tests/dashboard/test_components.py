from kiatracker.dashboard import components

EVIL = "<script>x</script> & co"


def test_every_builder_escapes_markup():
    outputs = (
        components.section_title(EVIL, EVIL),
        components.stat_strip([(EVIL, EVIL, EVIL)]),
        components.icon_list([("❄", components.theme.TINT_SKY, EVIL)]),
        components.chip(EVIL, "sky"),
        components.hidden_title(EVIL),
    )
    for out in outputs:
        assert "<script>" not in out and "&lt;script&gt;" in out and "&amp; co" in out


def test_fmt_ft_rounds_to_hundreds():
    assert components.fmt_ft(60176.4) == "60 200 Ft" and components.fmt_ft(49) == "0 Ft"


def test_stat_strip_has_one_cell_per_item():
    out = components.stat_strip([("Drives", "412", "this year"), ("Distance", "26 418 km", None)])
    assert out.count('class="wr-stat"') == 2 and "this year" in out


def test_hidden_title_is_an_h1():
    assert components.hidden_title("Range").startswith('<h1 class="wr-hidden">')
