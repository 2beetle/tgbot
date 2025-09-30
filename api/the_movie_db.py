import logging

from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from tmdbv3api import TMDb, TV, Genre, Movie
import telegram

from api.base import command
from config.config import TMDB_API_KEY, TMDB_POSTER_BASE_URL, get_allow_roles_command_map
from db.models.log import OperationLog, OperationType
from db.models.user import User
from utils.command_middleware import depends

logger = logging.getLogger(__name__)


async def format_tmdb_tv_search(data, genre_mapping, detail):
    genres = ", ".join(genre_mapping.get(gid, str(gid)) for gid in data.get('genre_ids', []))
    origin_countries = ", ".join(data.get('origin_country', []))

    homepage = detail.homepage
    formatted_text = f"""<b>🎬 剧概述</b>
<b>📌 剧名：</b>{data.get('name')}
<b>🌍 原名：</b>{data.get('original_name')}
<b>📅 首播日期：</b>{data.get('first_air_date')}
<b>🗣️ 语言：</b>{data.get('original_language')} (zh)
<b>🏳️ 产地：</b>{origin_countries}
<b>🎭 流派：</b>{genres}
<b>🔗 影视地址：</b><a href="{data.get('homepage')}">{data.get('homepage')}</a>

<b>📝 简介：</b>
{data.get('overview')[:200] + "..." if len(data.get('overview') or "") > 200 else data.get('overview') or '暂无简介'}

<b>⭐ 评分：</b>
平均评分: {data.get('vote_average')}
投票人数: {data.get('vote_count')}
    """

    # 最新一集信息
    detail = detail._dict()
    last_episode_to_air = detail.get('last_episode_to_air')
    if last_episode_to_air:
        last_episode_to_air_msg = f"""<b>📺 最新一集</b>
<b>📖 季号：</b>第 {last_episode_to_air.get('season_number')} 季
<b>🎞️ 集数：</b>第 {last_episode_to_air.get('episode_number')} 集
<b>📝 名称：</b>{last_episode_to_air.get('name')}
<b>🗒️ 概述：</b>{last_episode_to_air.get('overview')[:200] + "..." if len(last_episode_to_air.get('overview') or "") > 200 else last_episode_to_air.get('overview')}
<b>📅 播放日期：</b>{last_episode_to_air.get('air_date')}
<b>⏱️ 时长：</b>{last_episode_to_air.get('runtime')} 分钟
<b>⭐ 评分：</b>{last_episode_to_air.get('vote_average')}（{last_episode_to_air.get('vote_count')}人）
    """
    else:
        last_episode_to_air_msg = "<b>📺 最新一集</b>\n暂无数据"

    # 季信息
    seasons_msg = "<b>📚 集数目录</b>\n"
    if detail.get('seasons'):
        for season in detail.get('seasons'):
            seasons_msg += (
                f"<b>📖 {season.get('name')}</b>\n"
                f"📅 播放日期：{season.get('air_date')}\n"
                f"🎞️ 集数：{season.get('episode_count')}\n"
                f"⭐ 评分：{season.get('vote_average')}\n\n"
            )
    else:
        seasons_msg += "暂无信息\n"

    # 合并输出
    final_message = formatted_text + "\n" + last_episode_to_air_msg + "\n\n" + seasons_msg
    return final_message


async def format_tmdb_movie_search(data, genre_mapping):
    genres = ", ".join(genre_mapping.get(gid, str(gid)) for gid in data.get('genre_ids', []))

    formatted_text = f"""
<b>🎬 电影标题：</b> {data.get('title')}
<i>（{data.get('original_title')}）</i>

<b>📅 上映日期：</b> {data.get('release_date')}  
<b>🌐 语言：</b> {data.get('original_language').upper()}  
<b>🎭 流派：</b> {genres}  

<b>📝 简介：</b>  
{data.get('overview')}

<b>⭐ 评分：</b>  
▫️ 平均评分：<b>{data.get('vote_average')}</b>  
▫️ 投票人数：<b>{data.get('vote_count')}</b>  

<b>🔥 人气指数：</b> {data.get('popularity')}
    """

    return formatted_text.strip()


def tmdb_search_tv_build_keyboard(search_content: str, page: int, total_page: int) -> InlineKeyboardMarkup:
    buttons = []
    if page < total_page:
        buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"search_tv:{search_content} {page + 1}"))
    buttons.append(InlineKeyboardButton("🔍 查找资源", callback_data=f"search_media_resource:{search_content}"))
    return InlineKeyboardMarkup([buttons]) if buttons else None


@command(name='search_tv', description="搜索电视剧信息", args="{tv name}")
async def tmdb_search_tv(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    tmdb = TMDb()
    tmdb.api_key = TMDB_API_KEY
    poster_base_url = TMDB_POSTER_BASE_URL
    tmdb.language = 'zh'
    tmdb.debug = True

    tv = TV()
    genre = Genre()
    genre_tv_data = genre.tv_list()
    genre_mapping = {genre['id']: genre['name'] for genre in genre_tv_data['genres']}
    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="缺少剧名参数")
    search_content = context.args[0]
    page = context.args[1] if len(context.args) > 1 else 1
    search = tv.search(search_content, page=page)

    logger.info(f"TMDB search tv: {search_content} page: {page}")
    logger.info(f"total_pages: {search.get('total_pages')}")

    for index, res in enumerate(search.get('results', [])):
        detail = tv.details(res.get('id'))
        poster_path = detail.get('poster_path')
        photo_url = f"{poster_base_url}{poster_path}"
        message = await format_tmdb_tv_search(res, genre_mapping, detail)
        try:
            await update.message.reply_photo(photo=photo_url, caption=message, parse_mode="html")
        except telegram.error.BadRequest as e:
            logger.error(f"reply_photo (photo: {photo_url}, caption: {message}) error: {e}")

    keyboard = tmdb_search_tv_build_keyboard(search_content, page, search.get('total_pages'))
    await update.message.reply_text(
        text="可选择以下操作：",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

    OperationLog(
        user_id=user.id,
        operation=OperationType.READ,
        description=f"用户{user.tg_id} - {user.username} 搜索 TV {search_content} 信息"
    )


async def on_search_tv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 从 callback_data 中提取页码
    _, args = query.data.split(":")
    search_content, page = args.split(' ')
    context.args = [search_content, int(page)]

    await tmdb_search_tv(update, context, session, user)


def tmdb_search_movie_build_keyboard(search_content: str, page: int, total_page: int) -> InlineKeyboardMarkup:
    buttons = []
    if page < total_page:
        buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"search_movie:{search_content} {page + 1}"))
    buttons.append(InlineKeyboardButton("🔍 查找资源", callback_data=f"search_media_resource:{search_content}"))
    return InlineKeyboardMarkup([buttons]) if buttons else None


@command(name='search_movie', description="搜索电影信息", args="{movie name}")
async def tmdb_search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    tmdb = TMDb()
    tmdb.api_key = TMDB_API_KEY
    poster_base_url = TMDB_POSTER_BASE_URL
    tmdb.language = 'zh'
    tmdb.debug = True

    movie = Movie()
    genre = Genre()
    genre_movie_data = genre.movie_list()
    genre_mapping = {genre['id']: genre['name'] for genre in genre_movie_data['genres']}

    if len(context.args) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="缺少剧名参数")
    search_content = context.args[0]
    page = context.args[1] if len(context.args) > 1 else 1

    search = movie.search(search_content)

    logger.info(f"TMDB search movie: {search_content} page: {page}")
    logger.info(f"total_pages: {search.get('total_pages')}")

    for index, res in enumerate(search.get('results', [])):
        detail = movie.details(res.get('id'))
        poster_path = detail.get('poster_path')
        photo_url = f"{poster_base_url}{poster_path}"
        message = await format_tmdb_movie_search(res, genre_mapping)

        try:
            await update.message.reply_photo(photo=photo_url, caption=message, parse_mode="html")
        except telegram.error.BadRequest as e:
            logger.error(f"reply_photo (photo: {photo_url}, caption: {message}) error: {e}")

    keyboard = tmdb_search_movie_build_keyboard(search_content, page, search.get('total_pages'))
    await update.message.reply_text(
        text="可选择以下操作：",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    OperationLog(
        user_id=user.id,
        operation=OperationType.READ,
        description=f"用户{user.tg_id} - {user.username} 搜索 MOVIE {search_content} 信息"
    )

async def on_search_movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 从 callback_data 中提取页码
    _, args = query.data.split(":")
    search_content, page = args.split(' ')
    context.args = [search_content, int(page)]

    await tmdb_search_movie(update, context, session, user)


handlers = [
    CallbackQueryHandler(
        depends(allowed_roles=get_allow_roles_command_map().get('search_tv'))(on_search_tv_callback),
        pattern=r"^search_tv:.*$"),
    CallbackQueryHandler(
        depends(allowed_roles=get_allow_roles_command_map().get('search_movie'))(on_search_movie_callback),
        pattern=r"^search_movie:.*$")
]