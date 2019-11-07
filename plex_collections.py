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
from time import sleep, time
from plexapi.server import PlexServer
from progress.bar import Bar

CONFIG_FILE = 'config.yaml'
TMDB_URL = 'https://api.themoviedb.org/3'
POSTER_ITEM_LIMIT = 5
DEBUG = False
DRY_RUN = False
FORCE = False
LIBRARY_NAME = ''
CONFIG = dict()


def init(debug, dry_run=False, force=False, library_name=''):
    global DEBUG
    global DRY_RUN
    global FORCE
    global LIBRARY_NAME
    global CONFIG

    DEBUG = debug
    DRY_RUN = dry_run
    FORCE = force
    LIBRARY_NAME = library_name

    with open(CONFIG_FILE, 'r') as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    CONFIG['headers'] = {'X-Plex-Token': CONFIG['plex_token']}
    CONFIG['plex_collection_url'] = '%s/library/sections/%%s/all?type=18' % CONFIG['plex_url']
    CONFIG['plex_collection_items_url'] = '%s/library/metadata/%%s/children' % CONFIG['plex_url']
    CONFIG['plex_images_url'] = '%s/library/metadata/%%s/%%s?url=%%s' % CONFIG['plex_url']
    CONFIG['plex_images_upload_url'] = '%s/library/metadata/%%s/%%s?includeExternalMedia=1' % CONFIG['plex_url']
    CONFIG['plex_summary_url'] = '%s/library/sections/%%s/all?type=18&id=%%s&summary.value=%%s' % CONFIG['plex_url']

    CONFIG['tmdb_url'] = '%s/configuration?api_key=%s' % (TMDB_URL, CONFIG['tmdb_key'])
    CONFIG['tmdb_movie_url'] = '%s/movie/%%s?api_key=%s&language=%%s' % (TMDB_URL, CONFIG['tmdb_key'])
    CONFIG['tmdb_collection_url'] = '%s/collection/%%s?api_key=%s&language=%%s' % (TMDB_URL, CONFIG['tmdb_key'])
    CONFIG['tmdb_collection_image_url'] = '%s/collection/%%s/images?api_key=%s' % (TMDB_URL, CONFIG['tmdb_key'])
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


def update_both():
    print('\r\nUpdating Collection Posters and Summaries')
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()
    tmdb_configuration = get_tmdb_data(CONFIG['tmdb_url'])

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_NAME and LIBRARY_NAME != plex_section.title:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = get_plex_data(CONFIG['plex_collection_url'] % plex_section.key)
        i = 0

        for plex_collection in plex_collections:
            i += 1
            print('\r\n> %s [%s/%s]' % (plex_collection.attrib['title'], i, len(plex_collections)))

            plex_collection_id = plex_collection.attrib['ratingKey']
            plex_collection_movies = get_plex_data(CONFIG['plex_collection_items_url'] % plex_collection_id)

            update_summary(plex, plex_section, plex_collection, plex_collection_movies)
            update_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration)


def update_summaries():
    print('\r\nUpdating Collection Summaries')
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    print('\r\nYour movie libraries are:')

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_NAME and LIBRARY_NAME != plex_section.title:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = get_plex_data(CONFIG['plex_collection_url'] % plex_section.key)
        i = 0

        for plex_collection in plex_collections:
            i += 1
            print('\r\n> %s [%s/%s]' % (plex_collection.attrib['title'], i, len(plex_collections)))

            plex_collection_id = plex_collection.attrib['ratingKey']
            plex_collection_movies = get_plex_data(CONFIG['plex_collection_items_url'] % plex_collection_id)

            update_summary(plex, plex_section, plex_collection, plex_collection_movies)


def update_posters():
    print('\r\nUpdating Collection Posters')
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()
    tmdb_configuration = get_tmdb_data(CONFIG['tmdb_url'])

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_NAME and LIBRARY_NAME != plex_section.title:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = get_plex_data(CONFIG['plex_collection_url'] % plex_section.key)
        i = 0

        for plex_collection in plex_collections:
            i += 1
            print('\r\n> %s [%s/%s]' % (plex_collection.attrib['title'], i, len(plex_collections)))

            plex_collection_id = plex_collection.attrib['ratingKey']
            plex_collection_movies = get_plex_data(CONFIG['plex_collection_items_url'] % plex_collection_id)

            update_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration)


def update_summary(plex, plex_section, plex_collection, plex_collection_movies):
    if not FORCE and plex_collection.attrib['summary'].strip() != '':
        print('Summary Exists.')
        if DEBUG:
            print(plex_collection.attrib['summary'])
        return

    plex_collection_id = plex_collection.attrib['ratingKey']
    title = plex_collection.attrib['title']
    summary = get_tmdb_summary(plex, plex_collection_movies, title)

    if summary == '':
        print('No Summary Available.')
        return

    if DRY_RUN:
        print("Would Update Summary With: " + summary)
        return True

    requests.put(CONFIG['plex_summary_url'] % (plex_section.key, plex_collection_id, parse.quote(summary)),
                 data={}, headers=CONFIG['headers'])
    print('Summary Updated.')


def get_tmdb_summary(plex, plex_collection_movies, title):
    tmdb_collection_id, lang = get_tmdb_collection_id(plex, plex_collection_movies)
    tmdb_collection = get_tmdb_data(CONFIG['tmdb_collection_url'] % (tmdb_collection_id, lang))

    if lang == 'en':
        title = title + ' Collection'

    if tmdb_collection_id == -1:
        print('  Could not find a matching TMDB collection.')
    else:
        if tmdb_collection['name'] != title:
            print(
                '  Invalid collection, does not match with the TMDB collection: %s' % tmdb_collection['name'])

        if 'overview' in tmdb_collection:
            if DEBUG:
                print(tmdb_collection['overview'])
            return tmdb_collection['overview']
    return ''


def update_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration):
    poster_found = False

    for plex_collection_movie in plex_collection_movies:
        movie = plex.fetchItem(int(plex_collection_movie.attrib['ratingKey']))
        if check_poster(movie, plex_collection_id):
            poster_found = True
            break

    if not poster_found:
        print("Collection Poster Not Found!")
        check_for_default_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration)


def check_poster(movie, plex_collection_id):
    custom_poster_path = ''
    local_poster_path = ''

    for media in movie.media:
        for mediapart in media.parts:
            file_path = str(os.path.dirname(mediapart.file)) + "\\"

            if os.path.isfile(file_path + str(CONFIG['custom_poster_filename']) + '.jpg'):
                custom_poster_path = file_path + str(CONFIG['custom_poster_filename']) + '.jpg'
            elif os.path.isfile(file_path + str(CONFIG['custom_poster_filename']) + '.png'):
                custom_poster_path = file_path + str(CONFIG['custom_poster_filename']) + '.png'

            if custom_poster_path != '':
                if DEBUG:
                    print("Custom Collection Poster Exists")
                key = get_sha1(custom_poster_path)
                poster_exists = check_if_poster_is_uploaded(key, plex_collection_id)

                if poster_exists:
                    print("Using Custom Collection Poster")
                    return True

                if DRY_RUN:
                    print("Would Set Custom Collection Poster: " + custom_poster_path)
                    return True

                requests.post(CONFIG['plex_images_upload_url'] % (plex_collection_id, 'posters'),
                              data=open(custom_poster_path, 'rb'), headers=CONFIG['headers'])
                print("Custom Collection Poster Set")
                return True

            if os.path.isfile(file_path + str(CONFIG['local_poster_filename']) + '.jpg'):
                local_poster_path = file_path + str(CONFIG['local_poster_filename']) + '.jpg'
            elif os.path.isfile(file_path + str(CONFIG['local_poster_filename']) + '.png'):
                local_poster_path = file_path + str(CONFIG['local_poster_filename']) + '.png'

            if local_poster_path != '':
                if DEBUG:
                    print("Local Collection Poster Exists")
                key = get_sha1(local_poster_path)
                poster_exists = check_if_poster_is_uploaded(key, plex_collection_id)

                if poster_exists:
                    print("Using Local Collection Poster")
                    return True

                if DRY_RUN:
                    print("Would Set Local Collection Poster: " + local_poster_path)
                    return True

                requests.post(CONFIG['plex_images_upload_url'] % (plex_collection_id, 'posters'),
                              data=open(local_poster_path, 'rb'), headers=CONFIG['headers'])
                print("Local Collection Poster Set")
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


def check_for_default_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration):
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
        download_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration)


def download_poster(plex, plex_collection_movies, plex_collection_id, tmdb_configuration):
    tmdb_collection_id, lang = get_tmdb_collection_id(plex, plex_collection_movies)
    tmdb_collection_images = get_tmdb_data(CONFIG['tmdb_collection_image_url'] % tmdb_collection_id)
    poster_urls = get_image_urls(tmdb_collection_images, tmdb_configuration, 'posters', lang, POSTER_ITEM_LIMIT)
    upload_images_to_plex(poster_urls, plex_collection_id, 'posters')


def get_plex_data(url):
    r = requests.get(url, headers=CONFIG['headers'])
    return ElementTree.fromstring(r.text)


def get_image_urls(tmdb_collection_images, tmdb_configuration, image_type, lang, artwork_item_limit):
    result = []
    base_url = tmdb_configuration['images']['base_url'] + 'original'

    if image_type not in tmdb_collection_images or not tmdb_collection_images[image_type]:
        return result

    for i, image in enumerate(tmdb_collection_images[image_type]):
        # lower score for images that are not in the films native language or engligh
        if image['iso_639_1'] is not None and image['iso_639_1'] != 'en' and image['iso_639_1'] != lang:
            tmdb_collection_images[image_type][i]['vote_average'] = 0

        # boost the score for localized posters (according to the preference)
        if image['iso_639_1'] == lang:
            tmdb_collection_images[image_type][i]['vote_average'] += 1

    sorted_result = sorted(tmdb_collection_images[image_type], key=lambda k: k['vote_average'], reverse=True)

    return list(map(lambda x: base_url + x['file_path'], sorted_result[:artwork_item_limit]))


def upload_images_to_plex(images, plex_collection_id, image_type):
    if images:
        plex_selected_image = ''

        if not DRY_RUN:
            bar = Bar('  Downloading %s:' % image_type, max=len(images))

        for image in images:
            if DRY_RUN:
                print("Would Upload Poster: " + image)
                continue

            bar.next()

            requests.post(CONFIG['plex_images_url'] % (plex_collection_id, image_type, image), data={},
                          headers=CONFIG['headers'])

            if plex_selected_image == '':
                plex_selected_image = \
                    get_plex_image_url(CONFIG['plex_images_url'] % (plex_collection_id, image_type, image))

        if not DRY_RUN:
            bar.finish()

        # set the highest rated image as selected again
        if DRY_RUN:
            print("Would Change Selected Poster to: " + images[-1])
            return True

        requests.put(CONFIG['plex_images_url'] % (plex_collection_id, image_type[:-1], plex_selected_image),
                     data={}, headers=CONFIG['headers'])


def get_plex_image_url(plex_images_url):
    r = requests.get(plex_images_url, headers=CONFIG['headers'])
    root = ElementTree.fromstring(r.text)

    for child in root:
        if child.attrib['selected'] == '1':
            url = child.attrib['key']
            return url[url.index('?url=') + 5:]


def get_tmdb_collection_id(plex, plex_collection_movies):
    for plex_collection_movie in plex_collection_movies:
        movie = plex.fetchItem(int(plex_collection_movie.attrib['ratingKey']))
        lang = 'en'
        match = False
        if DEBUG:
            print('Movie guid: %s' % movie.guid)

        if movie.guid.startswith('com.plexapp.agents.imdb://'):  # Plex Movie agent
            match = re.search(r'tt[0-9]\w+', movie.guid)
        elif movie.guid.startswith('com.plexapp.agents.themoviedb://'):  # TheMovieDB agent
            match = re.search(r'[0-9]\w+', movie.guid)

        if not match:
            continue

        movie_id = match.group()

        match = re.search("lang=[a-z]{2}", movie.guid)

        if match:
            lang = match.group()[5:]

        movie_info = get_tmdb_data(CONFIG['tmdb_movie_url'] % (movie_id, lang))

        if movie_info and 'belongs_to_collection' in movie_info and movie_info['belongs_to_collection'] is not None:
            collection_id = movie_info['belongs_to_collection']['id']
            if DEBUG:
                print('  Retrieved collection id: %s (from: %s id: %s language: %s)'
                      % (collection_id, movie.title, movie_id, lang))
            return collection_id, lang

    return -1, ''


def get_tmdb_data(url, retry=True):
    try:
        r = requests.get(url)

        if 'X-RateLimit-Remaining' not in r.headers:
            print('Rate limit not returned, waiting to 5 seconds to retry')
            sleep(5)
            raise requests.exceptions.RequestException('Rate limit not returned')

        if DEBUG:
            print('Requests in time limit remaining: %s' % r.headers['X-RateLimit-Remaining'])

        if r.headers['X-RateLimit-Remaining'] == '1':
            wait = int(r.headers['X-RateLimit-Reset']) - int(time()) + 2
            print('Pausing for %s seconds, due to rate limit' % wait)
            sleep(wait)

        return r.json()
    except requests.exceptions.RequestException as e:
        if DEBUG:
            print(e)

        print('Error fetching JSON from The Movie Database: %s' % url)

        if retry:
            return get_tmdb_data(url, False)


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


@cli.command('setup')
def command_setup():
    setup()


@cli.command('run')
@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--library', '-l', default='')
def run(debug, dry_run, library):
    init(debug, dry_run, False, library)
    update_both()


@cli.command('update_summaries')
@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--force', '-f', default=False, is_flag=True, help='Overwrite existing data.')
@click.option('--library', '-l', default='')
def command_update_summaries(debug, dry_run, force, library):
    init(debug, dry_run, force, library)
    update_summaries()


@cli.command('update_posters')
@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--library', '-l', default='')
def command_update_posters(debug, dry_run, library):
    init(debug, dry_run, False, library)
    update_posters()


if __name__ == "__main__":
    cli()
