import json
from procyclingstats import Ranking, Rider, Race, Stage, RaceStartlist, RiderResults

INDIVIDUAL_RANKING_URL = "rankings.php?offset=0&id=me"
TEAM_RANKING_URL = "rankings.php?offset=0&id=te"

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


def get_individual_ranking(top_n: int = 20) -> list[dict]:
    try:
        ranking = Ranking(INDIVIDUAL_RANKING_URL)
        riders = ranking.riders()
        return riders[:top_n] if riders else []
    except Exception as e:
        return [{"error": f"Failed to fetch individual ranking: {e}"}]


def get_team_ranking(top_n: int = 20) -> list[dict]:
    try:
        ranking = Ranking(TEAM_RANKING_URL)
        teams = ranking.teams()
        return teams[:top_n] if teams else []
    except Exception as e:
        return [{"error": f"Failed to fetch team ranking: {e}"}]


def get_rider_profile(rider_slug: str) -> dict:
    try:
        rider = Rider(f"rider/{rider_slug}")
        return rider.info()
    except ValueError:
        return {"error": f"Rider '{rider_slug}' not found on PCS"}
    except Exception as e:
        return {"error": str(e)}


def get_rider_results(rider_slug: str, year: int | None = None) -> list[dict]:
    try:
        url = f"rider/{rider_slug}/results"
        if year:
            url += f"/{year}"
        rr = RiderResults(url)
        return rr.results()
    except ValueError:
        return [{"error": f"Results for '{rider_slug}' not found on PCS"}]
    except Exception as e:
        return [{"error": str(e)}]


def get_race_overview(race_slug: str, year: int) -> dict:
    try:
        race = Race(f"race/{race_slug}/{year}/result")
        results = race.results()
        info = {}
        try:
            info = race.info()
        except Exception:
            pass
        return {"info": info, "top_results": results[:10] if results else []}
    except ValueError:
        return {"error": f"Race '{race_slug}/{year}' not found on PCS"}
    except Exception as e:
        return {"error": str(e)}


def get_stage_results(race_slug: str, year: int, stage_num: int) -> dict:
    try:
        stage = Stage(f"race/{race_slug}/{year}/stage-{stage_num}")
        results = stage.results()
        return {"stage": stage_num, "results": results[:20] if results else []}
    except ValueError:
        return {"error": f"Stage {stage_num} of '{race_slug}/{year}' not found on PCS"}
    except Exception as e:
        return {"error": str(e)}


def get_race_startlist(race_slug: str, year: int) -> list[dict]:
    try:
        sl = RaceStartlist(f"race/{race_slug}/{year}/startlist")
        return sl.startlist()
    except ValueError:
        return [{"error": f"Startlist for '{race_slug}/{year}' not found on PCS"}]
    except Exception as e:
        return [{"error": str(e)}]
