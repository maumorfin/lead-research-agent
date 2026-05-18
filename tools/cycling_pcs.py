from tools.web_search import search

COMMON_RACE_SLUGS = {
    "tour de france": "tour-de-france",
    "tdf": "tour-de-france",
    "giro": "giro-d-italia",
    "giro d'italia": "giro-d-italia",
    "vuelta": "vuelta-a-espana",
    "vuelta a espana": "vuelta-a-espana",
    "milan san remo": "milano-sanremo",
    "paris roubaix": "paris-roubaix",
    "liege bastogne liege": "liege-bastogne-liege",
    "lbl": "liege-bastogne-liege",
    "ronde": "ronde-van-vlaanderen",
    "tour of flanders": "ronde-van-vlaanderen",
    "il lombardia": "il-lombardia",
    "worlds": "uci-road-world-championships",
    "strade bianche": "strade-bianche",
    "tirreno adriatico": "tirreno-adriatico",
    "criterium du dauphine": "criterium-du-dauphine",
}


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def _to_results(search_results) -> list[dict]:
    return [{"title": r.title, "url": r.url, "content": r.content} for r in search_results]


def get_individual_ranking(top_n: int = 20) -> list[dict]:
    results = search(f"UCI WorldTour individual rider ranking top {top_n} 2025 points standings")
    return _to_results(results)


def get_team_ranking(top_n: int = 20) -> list[dict]:
    results = search(f"UCI WorldTour team ranking top {top_n} 2025 points standings")
    return _to_results(results)


def get_rider_profile(rider_slug: str) -> dict:
    name = _slug_to_name(rider_slug)
    results = search(f"{name} professional cyclist profile career stats wins biography")
    return {"results": _to_results(results)}


def get_rider_results(rider_slug: str, year: int | None = None) -> list[dict]:
    name = _slug_to_name(rider_slug)
    year_str = str(year) if year else "2025"
    results = search(f"{name} cycling race results {year_str} victories podiums")
    return _to_results(results)


def get_race_overview(race_slug: str, year: int) -> dict:
    name = _slug_to_name(race_slug)
    results = search(f"{name} {year} race results GC classification winner podium")
    return {"results": _to_results(results)}


def get_stage_results(race_slug: str, year: int, stage_num: int) -> dict:
    name = _slug_to_name(race_slug)
    results = search(f"{name} {year} stage {stage_num} results winner finish")
    return {"stage": stage_num, "results": _to_results(results)}


def get_race_startlist(race_slug: str, year: int) -> list[dict]:
    name = _slug_to_name(race_slug)
    results = search(f"{name} {year} startlist riders teams participating")
    return _to_results(results)
