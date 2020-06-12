import argparse
import os
import subprocess

import re
import sys
import tempfile
from math import ceil
from pathlib import Path
from typing import Optional

import selenium
import eyed3

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.support.wait import WebDriverWait

DEFAULT_TAGS_EXTRACTOR = "((?P<artist>.*) - )?(?P<title>.*).mp3"
DEFAULT_COVER_RESOLUTION = 600

verbose = False
firefox: Optional[selenium.webdriver.Firefox] = None

def vprint(*args, **kwargs):
    if not verbose:
        return
    print(*args, **kwargs)


def init_driver(geckodriver: str, show: bool):
    global firefox
    if not firefox:
        # Init driver

        fo = Options()
        if not show:
            fo.add_argument('--headless')

        firefox = webdriver.Firefox(
            executable_path=geckodriver,
            options=fo
        )

def s(o, default="----") -> str:
    return o if o is not None else default

def google_fetch_album_name(song: str) -> Optional[str]:
    album = None

    firefox.get("https://www.google.com/")
    assert "Google" in firefox.title

    query_input = firefox.find_element_by_name("q") # <input>
    query_input.clear()
    query_input.send_keys(song)

    query_form = firefox.find_element_by_name("f") # <form>
    query_form.submit()

    try:
        wait = WebDriverWait(firefox, 5)
        wait.until(presence_of_element_located((By.CLASS_NAME, "zloOqf")))
        metadata_containers = firefox.find_elements_by_class_name("zloOqf")

        vprint(f"\t\t{len(metadata_containers)} metadata found")

        for metadata_container in metadata_containers:
            key = metadata_container.find_element_by_class_name("fl").text
            val = metadata_container.find_element_by_class_name("LrzXr").text
            vprint(f"\t\t\t{key} = {val}")

            if key == "Album":
                album = val # album found
                break

            if key == "Tipo album" or \
                key == "Generi" or \
                key == "Data di uscita" or \
                key == "Casa discografica":
                album = song # the song name is the album name
                break

    except Exception as e:
        vprint(f"\tCan't retrieve metadata for '{song}': {str(e)}")
        return None

    return album

def mp3norm(path: Path,
            extract: bool,
            extract_pattern: re.Pattern,
            download_cover: bool,
            cover_resolution: int,
            fetch_album_name: bool,
            driver: str,
            show_driver: bool,
            force: bool):

    # Ensure that is an mp3 file
    if not path or not path.is_file() or not path.name.endswith(".mp3"):
        return

    # Do we have something to do?
    if not extract and not download_cover and not fetch_album_name:
        vprint("\tSKIP")
        return

    # 1. Retrieve the mp3 tags
    mp3 = eyed3.load(path)

    artist = mp3.tag.artist
    title = mp3.tag.title
    album = mp3.tag.album
    covers = mp3.tag.images

    vprint("\tCURRENT TAGS")
    vprint(f"\t\tARTIST = {s(artist)}")
    vprint(f"\t\tTITLE  = {s(title)}")
    vprint(f"\t\tALBUM  = {s(album)}")
    vprint(f"\t\tCOVER  = {'yes' if covers else 'no'}")

    if artist and title and album and covers and not force:
        # Already fulfilled, nothing to do
        vprint("\tSKIP")
        return

    # 2. Extract the tags from the filename
    if extract and (not artist or not title or not album or force):
        match = re.search(extract_pattern, path.name)

        if not match:
            print("\tINVALID FILENAME")
            return

        d = match.groupdict()

        vprint("\tTAGS EXTRACTED FROM FILENAME")
        vprint(f"\t\tARTIST = {s(d.get('artist'))}")
        vprint(f"\t\tTITLE = {s(d.get('title'))}")
        vprint(f"\t\tALBUM = {s(d.get('album'))}")

        # The final tags are from the original tags if present, or extracted from the filename
        artist = artist or d.get("artist")
        title = title or d.get("title")
        album = album or d.get("album")


    # 3. Fetch the album name from Google Search
    if driver:
        init_driver(driver, show=show_driver)

    if (fetch_album_name or download_cover) and (not album or force):
        # Retrieve the album name in both cases
        song = f"{artist} {title}"
        vprint(f"\tFetching album name of '{song}'")
        album = google_fetch_album_name(f"{song}")
        vprint(f"\tFetched album name: '{album}'")


    cover_b = None

    if download_cover and (not covers or force):
        # Create a temporary file for the cover
        tmp_fd, tmp_name = tempfile.mkstemp(prefix="mp3norm-cover-", suffix=".jpg")

        # 4. Fetch the cover (using sacad)
        # sacad <artist> <album> <resolution> <cover_file>
        album_or_title = album or title

        try:
            vprint(f"\tFetching cover for (artist={artist} - album/title={album_or_title}) [saving into {tmp_name}]")
            args = ["sacad", artist, album_or_title, str(cover_resolution), tmp_name]
            if verbose:
                subprocess.run(args)
            else:
                subprocess.run(args, stderr=subprocess.DEVNULL)

        except Exception as e:
            vprint(f"\tCan't retrieve cover for (artist={artist} - album/title={album_or_title}): {str(e)}")

        # Check if something has been written
        cover_size = os.fstat(tmp_fd).st_size
        if cover_size:
            vprint(f"\tFetched cover of {ceil(cover_size / 1024)}KB")
            cover_b = os.read(tmp_fd, cover_size)

        # Close the temporary file
        os.close(tmp_fd)

        # Unlink the temporary file
        os.unlink(tmp_name)

    # 5. Set the tags (if something changed or force is given)
    vprint("\tDEFINITIVE TAGS")
    vprint(f"\t\tARTIST = {s(artist)}")
    vprint(f"\t\tTITLE  = {s(title)}")
    vprint(f"\t\tALBUM  = {s(album)}")
    vprint(f"\t\tCOVER  = {'yes' if cover_b else 'no'}")

    need_save = False

    if artist != mp3.tag.artist:
        mp3.tag.artist = artist
        need_save = True

    if title != mp3.tag.title:
        mp3.tag.title = title
        need_save = True

    if album != mp3.tag.album:
        mp3.tag.album = album
        need_save = True

    if cover_b:
        mp3.tag.images.set(3, cover_b, "image/jpeg")
        need_save = True

    # Skip save if not needed
    if need_save or force:
        mp3.tag.save()



def main():
    global verbose

    parser = argparse.ArgumentParser(description="Extract tags from filename and/or fetch album name/cover from Google Search (requires eyed3)")
    # --extract [<regex>]
    parser.add_argument("-e", "--extract", dest="extract", nargs="?", const=DEFAULT_TAGS_EXTRACTOR, default=False,
                        help=f"Extract tags from filename, using the (optional) "
                             f"regex (default is '{DEFAULT_TAGS_EXTRACTOR}'")
    # --album
    parser.add_argument("-a", "--album", dest="album", action="store_const", const=True, default=False,
                        help="Tries to retrieve the album name (requires selenium)")
    # --cover
    parser.add_argument("-c", "--cover", dest="cover", nargs="?", const=DEFAULT_COVER_RESOLUTION, default=False,
                        help="Download cover (using the optionally given resolution) and attach it to the file (requires sacad)")
    # --force
    parser.add_argument("-f", "--force", dest="force", action="store_const", const=True, default=False,
                        help="Force tag filling and cover retrieval even if are already present")
    # --verbose
    parser.add_argument("-v", "--verbose", dest="verbose", action="store_const", const=True, default=False,
                        help="Path of geckodriver")
    # --driver <driver>
    parser.add_argument("-d", "--driver", dest="driver",
                        help="Path of geckodriver")

    # --show-driver
    parser.add_argument("-s", "--show-driver", dest="show_driver", action="store_const", const=True, default=False,
                        help="Show the selenium web driver, if needed")

    parser.add_argument("input", nargs='?', default=".",
                        help=".mp3 file or folder containing the .mp3 files")

    # Read args
    parsed = vars(parser.parse_args(sys.argv[1:]))

    verbose = parsed.get("verbose")
    extract = parsed.get("extract")
    cover = parsed.get("cover")
    album = parsed.get("album")
    force = parsed.get("force")
    driver = parsed.get("driver")
    show_driver = parsed.get("show_driver")
    mp3_input = Path(parsed["input"])

    vprint(parsed)

    # Either -e, -c or -a must be given
    actions = [extract, cover, album]
    internet_actions = [cover, album]
    if actions.count(False) == len(actions):
        print("Nothing to do, either --extract, --cover or --album must be given")
        exit(-1)

    # Driver path must be given if cover and/or album name have to be retrieved
    if internet_actions.count(False) != len (internet_actions) and not driver:
        print("--driver must be given if --cover or --album is given")
        exit(-1)

    # Is regex valid (if given)?
    extract_pattern = None
    if extract:
        try:
            extract_pattern = re.compile(extract)
        except:
            print(f"Invalid extract regex: '{extract}'")
            exit(-1)

    # Is given path valid?
    if not mp3_input.exists():
        print(f"'{mp3_input}' does not exists")
        exit(-1)

    # Is a file or a directory?
    if mp3_input.is_file():
        mp3_input_files = mp3_input
    else:
        mp3_input_files = sorted(list(mp3_input.iterdir()))

    # Keep only .mp3 files
    mp3_input_files = [mp3 for mp3 in mp3_input_files if mp3.name.endswith(".mp3")]

    n = len(mp3_input_files)

    # mp3norm for each file
    for idx, mp3 in enumerate(mp3_input_files):
        print(f"[{str(idx + 1).rjust(len(str(n)))}/{n}] {mp3.name}")
        mp3norm(mp3,
                extract=True if extract_pattern else False,
                extract_pattern=extract_pattern,
                fetch_album_name=album,
                download_cover=True if cover else False,
                cover_resolution=cover,
                force=force,
                driver=driver,
                show_driver=show_driver)

    if firefox:
        firefox.close()

if __name__ == "__main__":
    main()