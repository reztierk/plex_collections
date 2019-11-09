#!/usr/bin/env python3

import re
import os
import yaml
import requests
import xml.etree.ElementTree as ElementTree
import click
import hashlib
import pprint as pretty
import urllib.parse as parse
import logging
from plexapi.server import PlexServer
from tmdbv3api import TMDb, Collection, Movie
from tmdbv3api import Configuration as TMDBConfiguration
from progress.bar import Bar

CONFIG_FILE = 'config.yaml'
POSTER_ITEM_LIMIT = 5
DEFAULT_AREAS = ['posters', 'summaries']
DEBUG = False
DRY_RUN = False
FORCE = False
LIBRARY_IDS = False
CONFIG = dict()
TMDB = TMDb()


def init(debug=False, dry_run=False, force=False, library_ids=False):
    global DEBUG
    global DRY_RUN
    global FORCE
    global LIBRARY_IDS
    global CONFIG
    global TMDB

    DEBUG = debug
    DRY_RUN = dry_run
    FORCE = force
    LIBRARY_IDS = library_ids

    if not DEBUG:
        logging.getLogger('tmdbv3api.tmdb').disabled = True

    with open(CONFIG_FILE, 'r') as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    CONFIG['headers'] = {'X-Plex-Token': CONFIG['plex_token']}
    CONFIG['plex_images_url'] = '%s/library/metadata/%%s/%%s?url=%%s' % CONFIG['plex_url']
    CONFIG['plex_images_upload_url'] = '%s/library/metadata/%%s/%%s?includeExternalMedia=1' % CONFIG['plex_url']
    CONFIG['plex_summary_url'] = '%s/library/sections/%%s/all?type=18&id=%%s&summary.value=%%s' % CONFIG['plex_url']

    TMDB.api_key = CONFIG['tmdb_key']
    TMDB.wait_on_rate_limit = True
    TMDB.language = 'en'

    if DEBUG:
        print('CONFIG: ')
        pretty.pprint(CONFIG)


def setup():
    try:
        data = dict()
        data['plex_url'] = click.prompt('Please enter your Plex URL', type=str)
        data['plex_token'] = click.prompt('Please enter your Plex Token', type=str)
        data['tmdb_key'] = click.prompt('Please enter your TMDB API Key', type=str)

        data['local_poster_filename'] = click.prompt(
            'Please enter the Local Poster filename (OPTIONAL)',
            default="movieset-poster",
            type=str
        )

        data['custom_poster_filename'] = click.prompt(
            'Please enter the Custom Poster filename (OPTIONAL)',
            default="movieset-poster-custom",
            type=str
        )

        with open(CONFIG_FILE, 'w') as outfile:
            yaml.dump(data, outfile, default_flow_style=False)
    except (KeyboardInterrupt, SystemExit):
        raise


def update(areas):
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_IDS and int(plex_section.key) not in LIBRARY_IDS:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = plex_section.collection()

        # Set TMDB language for section
        TMDB.language = plex_section.language

        for k, plex_collection in enumerate(plex_collections):
            print('\r\n> %s [%s/%s]' % (plex_collection.title, k + 1, len(plex_collections)))

            if 'posters' in areas:
                update_poster(plex_collection)

            if 'summaries' in areas:
                update_summary(plex_collection)


def list_libraries():
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))


def update_summary(plex_collection):
    if not FORCE and plex_collection.summary.strip() != '':
        print('Summary Exists.')
        if DEBUG:
            print(plex_collection.summary)
        return

    summary = get_tmdb_summary(plex_collection)

    if not summary:
        print('No Summary Available.')
        return

    if DRY_RUN:
        print("Would Update Summary With: " + summary)
        return True

    requests.put(CONFIG['plex_summary_url'] %
                 (plex_collection.librarySectionID, plex_collection.ratingKey, parse.quote(summary)),
                 data={}, headers=CONFIG['headers'])
    print('Summary Updated.')


def get_tmdb_summary(plex_collection_movies):
    tmdb_collection_id = get_tmdb_collection_id(plex_collection_movies)
    collection = Collection().details(collection_id=tmdb_collection_id)
    return collection.entries.get('overview')


def update_poster(plex_collection):
    poster_found = False
    for image_type in ['custom', 'local']:
        for movie in plex_collection.children:
            if check_posters(movie, plex_collection.ratingKey, image_type):
                return

    if not poster_found:
        print("Collection Poster Not Found!")
        check_for_default_poster(plex_collection)


def check_posters(movie, plex_collection_id, image_type):
    for media in movie.media:
        for media_part in media.parts:
            if check_poster(media_part, image_type, plex_collection_id):
                return True


def check_poster(media_part, image_type, plex_collection_id):
    file_path = str(os.path.dirname(media_part.file)) + os.path.sep + str(CONFIG[image_type + '_poster_filename'])
    poster_path = ''

    if os.path.isfile(file_path + '.jpg'):
        poster_path = file_path + '.jpg'
    elif os.path.isfile(file_path + '.png'):
        poster_path = file_path + '.png'

    if poster_path != '':
        if DEBUG:
            print("%s Collection Poster Exists" % image_type.capitalize())
        key = get_sha1(poster_path)
        poster_exists = check_if_poster_is_uploaded(key, plex_collection_id)

        if poster_exists:
            print("Using %s Collection Poster" % image_type.capitalize())
            return True

        if DRY_RUN:
            print("Would Set %s Collection Poster: %s" % (image_type.capitalize(), poster_path))
            return True

        requests.post(CONFIG['plex_images_upload_url'] % (plex_collection_id, 'posters'),
                      data=open(poster_path, 'rb'), headers=CONFIG['headers'])
        print(image_type.capitalize() + " Collection Poster Set")
        return True


def check_if_poster_is_uploaded(key, plex_collection_id):
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, 'posters', ''))
    key_prefix = 'upload://posters/'
    for image in images:
        if image.attrib['selected'] == '1':
            if image.attrib['ratingKey'] == key_prefix + key:
                return True
        if image.attrib['ratingKey'] == key_prefix + key:
            if DRY_RUN:
                print("Would Change Selected Poster to: " + image.attrib['ratingKey'])
                return True

            requests.put(CONFIG['plex_images_url'] % (plex_collection_id, 'poster', image.attrib['ratingKey']),
                         data={}, headers=CONFIG['headers'])
            return True


def check_for_default_poster(plex_collection):
    plex_collection_id = plex_collection.ratingKey
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, 'posters', ''))
    first_non_default_image = ''

    for image in images:
        if image.attrib['selected'] == '1' and image.attrib['ratingKey'] != 'default://':
            return True
        if first_non_default_image == '' and image.attrib['ratingKey'] != 'default://':
            first_non_default_image = image.attrib['ratingKey']

    if first_non_default_image != '':
        print('Default Plex Generated Poster Detected')

        if DRY_RUN:
            print("Would Change Selected Poster to: " + first_non_default_image)
            return True

        requests.put(CONFIG['plex_images_url'] % (plex_collection_id, 'poster', first_non_default_image),
                     data={}, headers=CONFIG['headers'])
        return True

    if int(images.attrib['size']) <= 1:
        download_poster(plex_collection)


def download_poster(plex_collection):
    plex_collection_id = plex_collection.ratingKey
    tmdb_collection_id = get_tmdb_collection_id(plex_collection)

    tmdb_collection_images = Collection().images(tmdb_collection_id)
    poster_urls = get_image_urls(tmdb_collection_images, 'posters', POSTER_ITEM_LIMIT)
    upload_images_to_plex(poster_urls, plex_collection_id, 'posters')


def get_plex_data(url):
    r = requests.get(url, headers=CONFIG['headers'])
    return ElementTree.fromstring(r.text)


def get_image_urls(tmdb_collection_images, image_type, artwork_item_limit):
    result = []
    base_url = TMDBConfiguration().info().images.get('base_url') + 'original'
    images = tmdb_collection_images.entries.get(image_type)

    if not images:
        return result

    for i, image in enumerate(images):
        # lower score for images that are not in the films native language or engligh
        if image['iso_639_1'] is not None and image['iso_639_1'] != 'en' and image['iso_639_1'] != TMDB.language:
            images[i]['vote_average'] = 0

        # boost the score for localized posters (according to the preference)
        if image['iso_639_1'] == TMDB.language:
            images[i]['vote_average'] += 1

    sorted_result = sorted(images, key=lambda k: k['vote_average'], reverse=True)

    return list(map(lambda x: base_url + x['file_path'], sorted_result[:artwork_item_limit]))


def upload_images_to_plex(images, plex_collection_id, image_type):
    if images:
        if DRY_RUN:
            for image in images:
                print("Would Upload Poster: " + image)
            print("Would Change Selected Poster to: " + images[-1])
            return True

        plex_selected_image = ''
        bar = Bar('  Downloading %s:' % image_type, max=len(images))

        for image in images:
            bar.next()
            requests.post(CONFIG['plex_images_url'] % (plex_collection_id, image_type, image), data={},
                          headers=CONFIG['headers'])

            if plex_selected_image == '':
                plex_selected_image = \
                    get_plex_image_url(CONFIG['plex_images_url'] % (plex_collection_id, image_type, image))

        bar.finish()

        # set the highest rated image as selected again
        requests.put(CONFIG['plex_images_url'] % (plex_collection_id, image_type[:-1], plex_selected_image),
                     data={}, headers=CONFIG['headers'])


def get_plex_image_url(plex_images_url):
    r = requests.get(plex_images_url, headers=CONFIG['headers'])
    root = ElementTree.fromstring(r.text)

    for child in root:
        if child.attrib['selected'] == '1':
            url = child.attrib['key']
            return url[url.index('?url=') + 5:]


def get_tmdb_collection_id(plex_collection):
    for movie in plex_collection.children:
        guid = movie.guid
        match = False

        if DEBUG:
            print('Movie guid: %s' % guid)

        if guid.startswith('com.plexapp.agents.imdb://'):  # Plex Movie agent
            match = re.search(r'tt[0-9]\w+', guid)
        elif guid.startswith('com.plexapp.agents.themoviedb://'):  # TheMovieDB agent
            match = re.search(r'[0-9]\w+', guid)

        if not match:
            continue

        movie = Movie().details(movie_id=match.group())

        if not movie.entries.get('belongs_to_collection'):
            return '-1'

        return movie.entries.get('belongs_to_collection').get('id')


def get_sha1(file_path):
    h = hashlib.sha1()

    with open(file_path, 'rb') as file:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            chunk = file.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


@click.group()
def cli():
    if not os.path.isfile(CONFIG_FILE):
        click.confirm('Configuration not found, would you like to set it up?', abort=True)
        setup()
        exit(0)
    pass


@cli.command('setup', help='Set Configuration Values')
def command_setup():
    setup()


@cli.command('run', help='Update Collection Posters and/or Summaries',
             epilog="eg: plex_collections.py run posters --dry-run --library=5 --library=8")
@click.argument('area', nargs=-1)
@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--force', '-f', default=False, is_flag=True, help='Overwrite existing data.')
@click.option('--library', default=False, multiple=True, type=int,
              help='Library ID to Update (Default all movie libraries)')
def run(debug, dry_run, force, library, area):
    for a in area:
        if a not in DEFAULT_AREAS:
            raise click.BadParameter('Invalid area argument(s), acceptable values are: %s' % '|'.join(DEFAULT_AREAS))

    if not area:
        area = DEFAULT_AREAS

    init(debug, dry_run, force, library)
    print('\r\nUpdating Collection %s' % ' and '.join(map(lambda x: x.capitalize(), area)))
    update(area)


@cli.command('list', help='List all Libraries')
def command_update_posters():
    init()
    print('\r\nUpdating Collection Posters')
    list_libraries()


if __name__ == "__main__":
    cli()
