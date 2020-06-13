import argparse
import os
import subprocess
import eyed3

import re
import sys
import tempfile
from math import ceil
from pathlib import Path
from typing import Optional, Any, NoReturn

""" AUTOMATICALLY GENERATED
usage: __main__.py [-h] [-e [REGEX]] [-a] [-c [RESOLUTION]] [-f] [-v] [-d GECKODRIVER] [-s] [input]

Extract tags from filename and/or fetch album name/cover from Google Search (requires eyed3)

positional arguments:
  input                 .mp3 file or folder containing the .mp3 files (default is current directory)

optional arguments:
  -h, --help            show this help message and exit
  -e [REGEX], --extract [REGEX]
                        Extract tags from filename, using the optional regex (default is "((?P<artist>.*) - )?(?P<title>.*).mp3")
  -a, --album           Tries to retrieve the album name (requires selenium)
  -c [RESOLUTION], --cover [RESOLUTION]
                        Download cover using the optional given resolution (default is 600) and attach it to the file (requires sacad)
  -f, --force           Force tag filling and cover retrieval even if are already present
  -v, --verbose         Print more messages
  -d GECKODRIVER, --driver GECKODRIVER
                        Path of the geckodriver (required if --album or --cover is given)
  -s, --show-driver     Show the selenium web driver, if needed
"""

DEFAULT_TAGS_EXTRACTOR = "((?P<artist>.*) - )?(?P<title>.*).mp3" # supports: artist, title, album
DEFAULT_COVER_RESOLUTION = 600

# Don't know if those will ever change
GOOGLE_META_CONTAINER_CLASSNAME = "zloOqf"
GOOGLE_META_KEY_CLASSNAME = "fl"
GOOGLE_META_VALUE_CLASSNAME = "LrzXr"

verbose = False
firefox: Any = None

cover_cache = {} # (artist,album) -> cover_data

def vprint(*args, **kwargs):
    if not verbose:
        return
    print(*args, **kwargs)


def abort(*args, **kwargs) -> NoReturn:
    print(*args, **kwargs)
    exit(-1)


def init_driver(geckodriver: str, show: bool):
    """
    Initializes selenium.
    :param geckodriver: path to the geckodriver (e.g. /opt/geckodriver/geckodriver)
    :param show: whether show the driver
    """
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options

    global firefox

    fo = Options()
    if not show:
        fo.add_argument('--headless')

    firefox = webdriver.Firefox(
        executable_path=geckodriver,
        options=fo,
        service_log_path=os.devnull
    )

def s(o, default="----") -> str:
    return o if o is not None else default

def google_fetch_album_name(artist: str, title: str) -> Optional[str]:
    """
    Tries to figure out the album name of the song described by
    'artist' and 'title' using Google search (using selenium/geckodriver).
    :param artist: the artist
    :param title: the title of the song
    :return: the probable album name
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.expected_conditions import presence_of_element_located
    from selenium.webdriver.support.wait import WebDriverWait

    album = None

    firefox.get("https://www.google.com/")
    assert "Google" in firefox.title

    query_input = firefox.find_element_by_name("q") # <input>
    query_input.clear()
    query_input.send_keys(f"{artist} {title}")

    query_form = firefox.find_element_by_name("f") # <form>
    query_form.submit()

    try:
        wait = WebDriverWait(firefox, 5)
        wait.until(presence_of_element_located((By.CLASS_NAME, GOOGLE_META_CONTAINER_CLASSNAME)))
        metadata_containers = firefox.find_elements_by_class_name("zloOqf")

        vprint(f"\t\t{len(metadata_containers)} metadata found")

        for metadata_container in metadata_containers:
            key = metadata_container.find_element_by_class_name(GOOGLE_META_KEY_CLASSNAME).text
            val = metadata_container.find_element_by_class_name(GOOGLE_META_VALUE_CLASSNAME).text
            vprint(f"\t\t\t{key} = {val}")

            if key == "Album":
                album = val # album found
                break

            if key == "Tipo album" or key == "Album type" or \
                key == "Generi" or key == "Genre" or \
                key == "Data di uscita" or key == "Release date" or \
                key == "Casa discografica" or key == "Label":
                album = title # the song name is the album name
                break

    except Exception:
        return None

    return album


def sacad_fetch_album_cover(artist: str, album: str, resolution: int) -> Optional[bytes]:
    """
    Retrieves the cover associated with 'artist' and 'album' (using sacad).
    :param artist: the artist
    :param album: the album name (the title is also ok)
    :param resolution: the desired resolution
    """
    # sacad <artist> <album> <resolution> <cover_file>


    # Just in case, check whether we have already downloaded this album
    cover_b = cover_cache.get((artist, album))
    if cover_b:
        return cover_b

    # Create a temporary file for the cover
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f"mp3norm-cover", suffix=".jpg")

    try:
        vprint(f"\tFetching cover for (artist={artist} - album/title={album}) [saving into {tmp_name}]")
        args = ["sacad", artist, album, str(resolution), "-t", "200", tmp_name]
        if verbose:
            subprocess.run(args)
        else:
            subprocess.run(args, stderr=subprocess.DEVNULL)

    except Exception as e:
        vprint(f"\tCan't retrieve cover for (artist={artist} - album/title={album}): {str(e)}")

    # Check if something has been written
    cover_size = os.fstat(tmp_fd).st_size
    if cover_size:
        vprint(f"\tFetched cover of {ceil(cover_size / 1024)}KB")
        cover_b = os.read(tmp_fd, cover_size)

    # Close the temporary file
    os.close(tmp_fd)

    # Unlink the temporary file
    os.unlink(tmp_name)

    # Update the cache
    cover_b = cover_cache[(artist, album)] = cover_b

    return cover_b


def mp3norm(path: Path,
            # -e / -E
            extract: bool,
            force_extract: bool,
            extract_pattern: re.Pattern,
            # -a / -A
            fetch_album_name: bool,
            force_fetch_album_name: bool,
            # -c / -C
            download_cover: bool,
            force_download_cover: bool,
            cover_resolution: int):
    """
    Performs mp3norm actions based on the parameters.
    :param path: mp3 file or directory of mp3 files to handle
    :param extract: whether extract tags from the filename
    :param force_extract: whether extract tags even if those as already present
    :param extract_pattern: the REGEX pattern to use for extraction
    :param fetch_album_name: whether fetch album name from Google Search
    :param force_fetch_album_name: whether fetch album name if already present
    :param download_cover: whether download the cover of the album
    :param force_download_cover: whether download the cover even if already present
    :param cover_resolution: the desired cover resolution
    """

    # Ensure that is an mp3 file
    if not path or not path.is_file() or not path.name.endswith(".mp3"):
        return

    # Do we have something to do?
    if not extract and not fetch_album_name and not download_cover:
        vprint("\tSKIP")
        return

    # 1. Retrieve the mp3 tags
    mp3 = eyed3.load(path)

    if not mp3:
        vprint(f"Can't load mp3 file: '{path}'")
        return

    if not mp3.tag:
        mp3.initTag()

    assert mp3.tag

    artist = mp3.tag.artist
    title = mp3.tag.title
    album = mp3.tag.album
    covers = mp3.tag.images

    vprint("\tCURRENT TAGS")
    vprint(f"\t\tARTIST = {s(artist)}")
    vprint(f"\t\tTITLE  = {s(title)}")
    vprint(f"\t\tALBUM  = {s(album)}")
    vprint(f"\t\tCOVER  = {'yes' if covers else 'no'}")

    # Do we actually have something to do?
    if (artist and title and album and covers) and \
            not ((extract and force_extract) or
                 (fetch_album_name and force_fetch_album_name) or
                 (download_cover and force_download_cover)):
        # Already fulfilled, nothing to do
        vprint("\tSKIP")
        return

    # 2. Extract the tags from the filename
    if extract and (not artist or not title or not album or force_extract):
        match = re.search(extract_pattern, path.name)

        if not match:
            print("\tINVALID FILENAME")
            return

        d = match.groupdict()

        vprint("\tTAGS EXTRACTED FROM FILENAME")
        vprint(f"\t\tARTIST = {s(d.get('artist'))}")
        vprint(f"\t\tTITLE  = {s(d.get('title'))}")
        vprint(f"\t\tALBUM  = {s(d.get('album'))}")

        # The final tags are from the original tags if present,
        # or extracted from the filename

        if not force_extract:
            # Use the new one only if not already present
            artist = artist or d.get("artist")
            title = title or d.get("title")
            album = album or d.get("album")
        else:
            # Give precedence to extraction
            artist = d.get("artist")
            title = d.get("title")
            album = d.get("album")

    # 3. Fetch the album name from Google Search

    if fetch_album_name and (not album or force_fetch_album_name):
        vprint(f"\tFetching album name of '{artist} - {title}'")
        album = google_fetch_album_name(artist, title)
        vprint(f"\tFetched album name: '{album}'")

    # 4. Fetch the cover (using sacad)

    cover_b = None

    if download_cover and (not covers or force_download_cover):
        cover_b = sacad_fetch_album_cover(artist, album or title, cover_resolution)

    # 5. Set the tags (if something changed or force is given)
    vprint("\tDEFINITIVE TAGS")
    vprint(f"\t\tARTIST = {s(artist)}")
    vprint(f"\t\tTITLE  = {s(title)}")
    vprint(f"\t\tALBUM  = {s(album)}")
    vprint(f"\t\tCOVER  = {'yes' if cover_b else 'no'}")

    need_save = False

    # Just a warning
    for t in [artist, title, album]:
        if t and (t.startswith(" ") or t.endswith(" ")):
            vprint(f"\tWARN: bad name/tags: '{path}'")

    def sanitize_tag(tagval):
        # Ignore non ASCII chars
        return str(tagval.strip().encode("ascii", "ignore"), encoding="utf-8") \
            if isinstance(tagval, str) else ""

    if artist != mp3.tag.artist:
        mp3.tag.artist = sanitize_tag(artist)
        need_save = True

    if title != mp3.tag.title:
        mp3.tag.title = sanitize_tag(title)
        need_save = True

    if album != mp3.tag.album:
        mp3.tag.album = sanitize_tag(album)
        need_save = True

    if cover_b:
        # Eventually remove previous covers (the one not assigned to description '')
        if covers:
            descs = [cover.description for cover in covers if cover.description]
            for desc in descs:
                covers.remove(desc)

        # Set the new cover
        covers.set(3, cover_b, "image/jpeg")
        need_save = True

    # Skip save if not needed
    if need_save:
        mp3.tag.save()
        vprint("\tSAVED")
    else:
        vprint("\tNOT SAVED")


def main():
    global verbose

    parser = argparse.ArgumentParser(
        description="Extract tags from filename and/or "
                    "fetch album name/cover from Google Search."
    )

    # --extract [<regex>]
    parser.add_argument("-e", "--extract",
                        nargs="?", const=DEFAULT_TAGS_EXTRACTOR, default=False,
                        dest="extract", metavar="REGEX",
                        help=f"Extract tags from filename if those are missing, using the optional "
                             f"regex (default is \"{DEFAULT_TAGS_EXTRACTOR}\")")
    # --force-extract [<regex>]
    parser.add_argument("-E", "--force-extract",
                        nargs="?", const=DEFAULT_TAGS_EXTRACTOR, default=False,
                        dest="force_extract", metavar="REGEX",
                        help=f"Extract tags from filename (always overwriting the previous values), "
                             f"using the optional regex (default is \"{DEFAULT_TAGS_EXTRACTOR}\")")
    # --album
    parser.add_argument("-a", "--album",
                        action="store_const", const=True, default=False,
                        dest="album",
                        help="If the album tag is missing, tries to retrieve the album name (requires selenium)")
    # --force-album
    parser.add_argument("-A", "--force-album",
                        action="store_const", const=True, default=False,
                        dest="force_album",
                        help="Always tries to retrieve the album name (requires selenium)")
    # --cover
    parser.add_argument("-c", "--cover",
                        nargs="?", const=DEFAULT_COVER_RESOLUTION, default=False,
                        dest="cover", metavar="RESOLUTION",
                        help=f"Download the cover, if it is missing, download it using the optional given resolution "
                             f"(default is {DEFAULT_COVER_RESOLUTION}) (requires sacad)")
    # --force-cover
    parser.add_argument("-C", "--force-cover",
                        nargs="?", const=DEFAULT_COVER_RESOLUTION, default=False,
                        dest="force_cover", metavar="RESOLUTION",
                        help=f"Always download the cover using the optional given resolution "
                             f"(default is {DEFAULT_COVER_RESOLUTION}) (requires sacad)")
    # --verbose
    parser.add_argument("-v", "--verbose",
                        action="store_const", const=True, default=False,
                        dest="verbose",
                        help="Print more messages")
    # --driver <driver>
    parser.add_argument("-d", "--driver",
                        dest="driver", metavar="GECKODRIVER",
                        help="Path of the geckodriver (required if --album is given)")
    # --show-driver
    parser.add_argument("-s", "--show-driver",
                        action="store_const", const=True, default=False,
                        dest="show_driver",
                        help="Show the selenium web driver, if used")

    # positional argument
    parser.add_argument("input",
                        nargs='?', default=".",
                        help=".mp3 file or folder containing the .mp3 files (default is current directory)")

    # Read args
    parsed = vars(parser.parse_args(sys.argv[1:]))

    extract = parsed.get("extract")
    force_extract = parsed.get("force_extract")
    cover = parsed.get("cover")
    force_cover = parsed.get("force_cover")
    album = parsed.get("album")
    force_album = parsed.get("force_album")
    verbose = parsed.get("verbose")
    driver = parsed.get("driver")
    show_driver = parsed.get("show_driver")
    mp3_input = Path(parsed["input"]).expanduser()

    vprint(parsed)

    # Check that only one between the action the forced action is given (e.g -e -E)
    if extract and force_extract:
        abort("Only one between -e and -E could be given")

    if cover and force_cover:
        abort("Only one between -c and -C could be given")

    if album and force_album:
        abort("Only one between -a and -A could be given")

    extract_regex = extract or force_extract # one of the given REGEX
    cover_resolution = cover or force_cover # one of the given RESOLUTION
    do_extract = True if (extract or force_extract) else False
    do_cover = True if (cover or force_cover) else False
    do_album = True if (album or force_album) else False
    dos = [do_extract, do_cover, do_album]

    if not dos.count(True):
        abort("No action given, either --[force-]extract, "
              "--[force-]cover or --[force-]album must be given")

    # Initialize selenium driver, if needed
    if do_album:
        # Driver path must be given album name have to be retrieved

        if not driver:
            abort("--driver DRIVER must be given if --album is given")

        init_driver(driver, show_driver)

    # Is regex valid (if given)?
    extract_pattern = None
    if extract_regex:
        try:
            extract_pattern = re.compile(extract_regex)
        except:
            abort(f"Invalid extract regex: '{extract_regex}'")

    # Is given path valid?
    if not mp3_input.exists():
        abort(f"'{mp3_input}' does not exists")

    # Is a file or a directory?
    if mp3_input.is_file():
        mp3_input_files = [mp3_input]
    else:
        mp3_input_files = sorted(list(mp3_input.iterdir()))

    # Keep only .mp3 files
    mp3_input_files = [mp3 for mp3 in mp3_input_files if mp3.name.endswith(".mp3")]

    n = len(mp3_input_files)

    # mp3norm for each file
    for idx, mp3 in enumerate(mp3_input_files):
        print(f"[{str(idx + 1).rjust(len(str(n)))}/{n}] {mp3.name}")
        mp3norm(mp3,
                extract=do_extract,
                force_extract=force_extract,
                extract_pattern=extract_pattern,
                fetch_album_name=do_album,
                force_fetch_album_name=force_album,
                download_cover=do_cover,
                force_download_cover=force_cover,
                cover_resolution=cover_resolution)

    if firefox:
        firefox.close()

if __name__ == "__main__":
    main()