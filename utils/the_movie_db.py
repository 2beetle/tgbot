import logging

from tmdbv3api import TMDb, TV, Genre

from config.config import TMDB_API_KEY, TMDB_POSTER_BASE_URL

logger = logging.getLogger(__name__)

class TheMovieDB:
    def __init__(self):
        self.tmdb = TMDb()
        self.tmdb.api_key = TMDB_API_KEY
        self.poster_base_url = TMDB_POSTER_BASE_URL
        self.tmdb.language = 'zh'
        self.tmdb.debug = True

    async def search_tv(self, tv_name, count=10):
        tv = TV()
        search = tv.search(tv_name, page=1)

        if search.get("total_results") == 0:
            return []

        logger.info(f"TMDB search tv: {tv_name}")

        results = []

        for index, res in enumerate(search):
            if len(results) >= count:
                break
            detail = tv.details(res.get('id'))
            poster_path = detail.get('poster_path')
            photo_url = f"{self.poster_base_url}{poster_path}"
            results.append({
                'name': detail.get('name'),
                'first_air_date': detail.get('first_air_date'),
                'photo_url': photo_url,
            })
        return results