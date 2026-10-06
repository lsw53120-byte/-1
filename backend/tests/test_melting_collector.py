import unittest

from app.collectors.melting import parse_rising_ranking


def ranking_page(*, ranks=(1, 2, 3)) -> str:
    cards = "".join(
        f'<div class="ranking-multi-row-card"><a href="/ko/app/characters/00000000-0000-0000-0000-{rank:012d}">'
        f'<span class="text-xl font-bold">{rank}</span><h3>Character {rank}</h3></a></div>'
        for rank in ranks
    )
    return f'<section><h2>Unrelated characters</h2><a href="/ko/app/characters/other">Ignore</a></section><section><h2>라이징 인기 랭킹</h2>{cards}</section>'


class MeltingCollectorParserTest(unittest.TestCase):
    def test_reads_only_ranking_section_in_rank_order(self):
        items = parse_rising_ranking(ranking_page(ranks=(3, 1, 2)), expected_count=3)
        self.assertEqual([1, 2, 3], [item.rank for item in items])
        self.assertEqual("Character 1", items[0].name)
        self.assertTrue(items[0].source_url.startswith("https://melting.chat/ko/app/characters/"))

    def test_rejects_missing_or_duplicate_positions(self):
        with self.assertRaises(ValueError):
            parse_rising_ranking(ranking_page(ranks=(1, 3)), expected_count=3)
        with self.assertRaises(ValueError):
            parse_rising_ranking(ranking_page(ranks=(1, 1, 2)), expected_count=3)

    def test_rejects_missing_section(self):
        with self.assertRaises(ValueError):
            parse_rising_ranking("<html><body></body></html>", expected_count=3)
