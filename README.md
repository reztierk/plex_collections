# plex_collections
This script is intended to be used to automatically update/check your Plex collection posters and summaries.

##### Posters:
Iterates through each collection checking the movies associated for the presence of a custom/local collection poster 
within the movie's directory (supports images with either '.png' or '.jpg' file extensions). 'local' is intended for
automatically scraped assets from tools like tinyMediaManager, where 'custom' is intended for manually acquired assets
you wish to be given priority. If local or custom posters are not found, it will attempt to download the top 5 
collection posters from TMDB based on rating and appropriate language (determined by the language set on the Library the
collection belongs to). On subsequent runs it will validate that the local assets are correctly selected when one is 
available, and detect when the default Plex generated poster is being used and select a different image to use if
available.

##### Summaries:
Iterates through each collection checking if they contain a summary. If the summary is blank it will attempt to retrieve
the one from TMDB (there is also a 'force' option which will update the summaries without checking if they are blank first).

# Installation
    git clone https://github.com/reztierk/plex_collections.git
    cd plex_collections
    pip install -r requirements.txt

# Usage

### setup
Used to set the required configuration values (triggered automatically of config.yaml is not found during script initialization).

    plex_collections.py setup

Required values:
 - Plex URL 
    - URL of the Plex instance you wish to use (eg. http://localhost:32400)
 - Plex Token
    - Token to be used for authenticated with Plex (see: https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
 - TMDB Key
    - API key to be used with TMDB (see: https://developers.themoviedb.org/3/getting-started/introduction)
 - Local Poster Filename
    - Filename of local posters without the file extension (default: movieset-poster)
 - Custom Poster Filename
    - Filename of custom posters without the file extension (default: movieset-poster-custom)

### list
Used to list all available Libraries (useful for easily obtaining a libraries ID)

    plex_collections.py list
    
### run
Update Collections, by default it will update both posters and summaries but can target one or the other specifically by
passing them as arguments. Can also be used with `--dry-run` to test before making changes, or `--library` to update 
only a specific libraries collections.

    # Both posters and summaries
    plex_collections.py run
    
    # Just posters
    plex_collections.py run posters
    
    # Just summaries
    plex_collections.py run summaries
    

Options: 
    
    -v, --debug
    -d, --dry-run
    -f, --force        Overwrite existing data.
    --library INTEGER  Library ID to Update (Default all movie libraries)

