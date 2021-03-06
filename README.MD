# MP3NORM

Simple script written in Python that extract tags from filename and/or fetch album name/cover from Google Search.

## REQUIREMENTS

* `eyed3`
* `sacad` (only for download albums covers)
* `selenium` (only for fetch albums names)

## INSTALLATION
```
pip install mp3norm
```

or 

```
git clone https://github.com/Docheinstein/mp3norm
```

## USAGE

Run with
```
python -m mp3norm
```

or 

```
mp3norm
```

```
python mp3norm.py [-h] [-e [REGEX]] [-E [REGEX]] [-a] [-A] [-c [RESOLUTION]] [-C [RESOLUTION]] [-v] [-d GECKODRIVER] [-s] [input]

positional arguments:
  input                 .mp3 file or folder containing the .mp3 files (default is current directory)

optional arguments:
  -h, --help            show this help message and exit
  -e [REGEX], --extract [REGEX]
                        Extract tags from filename if those are missing, using the optional regex (default is "((?P<artist>.*) - )?(?P<title>.*).mp3")
  -E [REGEX], --force-extract [REGEX]
                        Extract tags from filename (always overwriting the previous values), using the optional regex (default is "((?P<artist>.*) - )?(?P<title>.*).mp3")
  -a, --album           If the album tag is missing, tries to retrieve the album name (requires selenium)
  -A, --force-album     Always tries to retrieve the album name (requires selenium)
  -c [RESOLUTION], --cover [RESOLUTION]
                        Download the cover, if it is missing, download it using the optional given resolution (default is 600) (requires sacad)
  -C [RESOLUTION], --force-cover [RESOLUTION]
                        Always download the cover using the optional given resolution (default is 600) (requires sacad)
  -v, --verbose         Print more messages
  -d GECKODRIVER, --driver GECKODRIVER
                        Path of the geckodriver (required if --album is given)
  -s, --show-driver     Show the selenium web driver, if used
```

## EXAMPLES

* Extract the mp3 tags for each mp3 file (with the format "\<artist\> - \<title\>.mp3)")
```
mp3norm /home/user/Music -e
```

* Fetch the album name for each mp3 file

```
mp3norm /home/user/Music -a
```

* Download the cover for each mp3 file

```
mp3norm /home/user/Music -c -d /opt/geckodriver/geckodriver
```


* Extract the mp3 tags, automatically fetch album name and cover

```
mp3norm /home/user/Music -e -a -c -d /opt/geckodriver/geckodriver
```


* Force to extract the mp3 tags, automatically fetch album name and cover 

```
mp3norm /home/user/Music -E -A -C -d /opt/geckodriver/geckodriver
```

* Extract the mp3 tags for a mp3 file with a non-default pattern

```
mp3norm "/home/user/Music/Fleetwood Mac - Rhiannon.mp3" -e "(?P<artist>.*)-(?P<title>.*)"
```

* Extract different mp3 tags for a mp3 file with a non-default pattern

```
mp3norm "Pink Floyd - The Dark Side of the Moon - Money.mp3" -e "(?P<artist>.*) - (?P<album>.*) - (?P<title>.*)"
```