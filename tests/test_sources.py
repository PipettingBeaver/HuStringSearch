"""Source parsers and registry behavior, using small on-disk fixtures."""

from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd
import pytest

from hustring.config import SourceConfig
from hustring.errors import SourceError
from hustring.sources import available_sources, create_source
from hustring.sources.biogrid import parse_biogrid
from hustring.sources.custom_tsv import CustomTSVSource
from hustring.sources.huri import parse_huri
from hustring.sources.intact import parse_intact
from hustring.sources.orthology import parse_cog_mappings
from hustring.sources.string import (
    StringSource,
    info_filename,
    links_filename,
    parse_info,
    parse_links,
)


def write_gz(path: Path, text: str) -> Path:
    with gzip.open(path, "wt") as handle:
        handle.write(text)
    return path


def test_string_links_parsing_and_threshold(tmp_path: Path) -> None:
    path = write_gz(
        tmp_path / "links.txt.gz",
        "protein1 protein2 combined_score\n"
        "9606.ENSP1 9606.ENSP2 900\n"
        "9606.ENSP1 9606.ENSP3 100\n",
    )
    all_edges = parse_links(path)
    assert all_edges["weight"].tolist() == pytest.approx([0.9, 0.1])

    filtered = parse_links(path, min_score=700)
    assert len(filtered) == 1
    assert filtered.iloc[0]["weight"] == pytest.approx(0.9)


def test_string_info_parsing(tmp_path: Path) -> None:
    path = write_gz(
        tmp_path / "info.txt.gz",
        "#string_protein_id\tpreferred_name\tprotein_size\tannotation\n"
        "9606.ENSP1\tTP53\t393\tTumor protein p53\n",
    )
    nodes = parse_info(path)
    assert nodes.iloc[0]["id"] == "9606.ENSP1"
    assert nodes.iloc[0]["symbol"] == "TP53"


def test_string_source_roundtrip(tmp_path: Path) -> None:
    taxid = 9606
    links = write_gz(
        tmp_path / links_filename(taxid, "12.0"),
        "protein1 protein2 combined_score\n9606.ENSP1 9606.ENSP2 800\n",
    )
    info = write_gz(
        tmp_path / info_filename(taxid, "12.0"),
        "#string_protein_id\tpreferred_name\tprotein_size\tannotation\n"
        "9606.ENSP1\tTP53\t393\tp53\n",
    )
    data = StringSource().parse({links.name: links, info.name: info}, taxid=taxid)
    assert data.n_edges == 1
    assert data.n_nodes == 1
    assert data.nodes.iloc[0]["symbol"] == "TP53"


def test_huri_parsing(tmp_path: Path) -> None:
    path = tmp_path / "HuRI.tsv"
    path.write_text("ENSG00000000005\tENSG00000061656\nENSG00000000005\tENSG00000099968\n")
    edges = parse_huri(path)
    assert len(edges) == 2
    assert edges["weight"].tolist() == [1.0, 1.0]
    assert edges.iloc[0]["a"].startswith("ENSG")


def test_custom_tsv_with_header_and_weight(tmp_path: Path) -> None:
    path = tmp_path / "edges.tsv"
    path.write_text("# comment\na\tb\tweight\nX\tY\t0.5\nY\tZ\t1.5\n")
    data = CustomTSVSource(path, a_col="a", b_col="b", weight_col="weight").parse(
        {}, taxid=9606
    )
    assert len(data.edges) == 2
    assert data.edges["weight"].tolist() == [0.5, 1.5]


def test_custom_tsv_default_weight(tmp_path: Path) -> None:
    path = tmp_path / "edges.tsv"
    path.write_text("X\tY\n")
    data = CustomTSVSource(path, header=None, default_weight=2.0).parse({}, taxid=9606)
    assert data.edges.iloc[0]["weight"] == pytest.approx(2.0)


def test_biogrid_filters_by_taxon(tmp_path: Path) -> None:
    path = tmp_path / "BIOGRID.tab3.txt"
    path.write_text(
        "Official Symbol Interactor A\tOfficial Symbol Interactor B\t"
        "Organism ID Interactor A\tOrganism ID Interactor B\n"
        "TP53\tMDM2\t9606\t9606\n"
        "Trp53\tMdm2\t10090\t10090\n"
    )
    edges, nodes = parse_biogrid(path, 9606)
    assert edges["a"].tolist() == ["TP53"]
    assert edges["b"].tolist() == ["MDM2"]
    assert set(nodes["id"]) == {"TP53", "MDM2"}


def test_intact_parsing_and_filtering(tmp_path: Path) -> None:
    path = tmp_path / "intact.txt"
    human = [
        "uniprotkb:P04637",
        "uniprotkb:Q00987",
        "-",
        "-",
        "-",
        "-",
        "psi-mi:MI:0004",
        "-",
        "-",
        "taxid:9606(human)",
        "taxid:9606(human)",
        "psi-mi:MI:0914",
        "psi-mi:MI:0469",
        "intact:EBI-1",
        "intact-miscore:0.53",
    ]
    mouse = list(human)
    mouse[0] = "uniprotkb:P02340"
    mouse[1] = "uniprotkb:P23804"
    mouse[9] = "taxid:10090(mouse)"
    mouse[10] = "taxid:10090(mouse)"
    path.write_text("\t".join(human) + "\n" + "\t".join(mouse) + "\n")

    edges, _ = parse_intact(path, 9606)
    assert len(edges) == 1
    assert edges.iloc[0]["a"] == "P04637"
    assert edges.iloc[0]["weight"] == pytest.approx(0.53)


def test_cog_bridge_cross_species_only(tmp_path: Path) -> None:
    path = tmp_path / "COG.mappings.txt"
    path.write_text(
        "#protein\tstart_position\tend_position\torthologous_group\tprotein_annotation\n"
        "9606.ENSP1\t1\t100\tCOG0001\thuman a\n"
        "9606.ENSP2\t1\t100\tCOG0001\thuman b\n"
        "511145.b0001\t1\t100\tCOG0001\tecoli\n"
        "9606.ENSP3\t1\t100\tCOG0002\tlonely\n"
    )
    edges, nodes = parse_cog_mappings(path, [9606, 511145])
    pairs = set(zip(edges["a"], edges["b"], strict=True))
    assert ("9606.ENSP1", "511145.b0001") in pairs
    assert ("9606.ENSP2", "511145.b0001") in pairs
    assert ("9606.ENSP1", "9606.ENSP2") not in pairs
    assert "9606.ENSP3" not in set(nodes["id"])


def test_cog_bridge_can_include_within_species(tmp_path: Path) -> None:
    path = tmp_path / "COG.mappings.txt"
    path.write_text(
        "#protein\tstart_position\tend_position\torthologous_group\tprotein_annotation\n"
        "9606.ENSP1\t1\t100\tCOG0001\thuman a\n"
        "9606.ENSP2\t1\t100\tCOG0001\thuman b\n"
    )
    edges, _ = parse_cog_mappings(path, [9606], include_within_species=True)
    assert len(edges) == 1


def test_registry_lists_and_creates_sources() -> None:
    names = available_sources()
    assert {"string", "huri", "biogrid", "intact", "custom", "orthology"} <= set(names)
    source = create_source(SourceConfig(name="string", options={"min_score": 700}))
    assert isinstance(source, StringSource)
    assert source.min_score == 700


def test_registry_unknown_source_raises() -> None:
    with pytest.raises(SourceError):
        create_source(SourceConfig(name="does-not-exist"))


def test_registry_invalid_options_raise() -> None:
    with pytest.raises(SourceError):
        create_source(SourceConfig(name="string", options={"nope": 1}))


def test_node_dataframe_is_immutable_shape(tmp_path: Path) -> None:
    path = tmp_path / "HuRI.tsv"
    path.write_text("ENSG1\tENSG2\n")
    from hustring.sources import SourceData

    data = SourceData(source="huri", edges=parse_huri(path))
    assert list(data.nodes.columns) == ["id", "symbol", "description"]
    assert data.n_nodes == 2
    assert isinstance(data.edges, pd.DataFrame)
