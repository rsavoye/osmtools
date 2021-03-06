#!/usr/bin/python3

# 
# Copyright (C) 2019, 2020   Free Software Foundation, Inc.
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# 

# ogr2ogr -t_srs EPSG:4326 Roads-new.shp hwy_road_aerial.shp

# lynx  https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/14/6193/3359
# lynx https://c.tile.opentopomap.org/14/3359/6193.png
# lynx https://caltopo.s3.amazonaws.com/topo/13/1679/3096.png

import os
import sys
import logging
import getopt
import epdb
from osgeo import gdal,ogr,osr
from sys import argv
sys.path.append(os.path.dirname(argv[0]) + '/osmpylib')
import urllib.request
import math
import mercantile
from tiledb import Tile
from tiledb import Tiledb
# import rasterio
# from rasterio.merge import merge
# from rasterio.enums import ColorInterp
import overpy
#import osm
import glob
import urllib.request
from urllib.parse import urlparse
from poly import Poly
from osm import osmConvert
from datetime import timedelta, datetime


class myconfig(object):
    def __init__(self, argv=list()):
        # Read the config file to get our OSM credentials, if we have any
        file = os.getenv('HOME') + "/.gosmrc"
        try:
            gosmfile = open(file, 'r')
        except Exception as inst:
            logging.warning("Couldn't open %s for writing! not using OSM credentials" % file)
            return
         # Default values for user options
        self.options = dict()
        self.options['logging'] = True
        self.options['verbose'] = False
        self.options['zooms'] = None
        self.options['poly'] = ""
        self.options['source'] = "ersi,topo,usgs,terrain"
        self.options['format'] = "gtiff"
        #self.options['force'] = False
        self.options['outfile'] = "./"
        # FIXME: 
        self.options['mosaic'] = False
        self.options['download'] = False
        self.options['ersi'] = False
        self.options['usgs'] = False
        self.options['topo'] = False
        self.options['terrain'] = False
        self.options['gtiff'] = False
        self.options['pdf'] = False
        self.options['osmand'] = False

        try:
            (opts, val) = getopt.getopt(argv[1:], "h,o:,s:,p:,v,z:,f:,d,m,n",
                ["help", "outfile", "source", "poly", "verbose", "zooms", "format", "download", "mosaic", "nodata"])
        except getopt.GetoptError as e:
            logging.error('%r' % e)
            self.usage(argv)
            quit()

        for (opt, val) in opts:
            if opt == '--help' or opt == '-h':
                self.usage(argv)
            elif opt == "--outfile" or opt == '-o':
                self.options['outfile'] = val
            elif opt == "--source" or opt == '-s':
                self.options['source'] = val
            elif opt == "--poly" or opt == '-p':
                self.options['poly'] = val
            elif opt == "--download" or opt == '-d':
                self.options['download'] = True
            elif opt == "--mosaic" or opt == '-m':
                self.options['mosaic'] = True
            elif opt == "--zooms" or opt == '-z':
                self.options['zooms'] = ( val.split(',' ) )
            elif opt == "--format" or opt == '-f':
                self.options['format'] = val
            elif opt == "--nodata" or opt == '-n':
                self.options['nodata'] = True
            elif opt == "--verbose" or opt == '-v':
                self.options['verbose'] = True
                logging.basicConfig(filename='tiler.log',level=logging.DEBUG)

    def checkOptions(self):
        """Range check some of the ptions here to reduce cutter when parsing"""
        logging.info("Range check options")
        if self.options['poly'] == None:
            print("ERROR: need to specify a polygon!")
            usage()
        for name, val in self.options.items():
            print("\t%s: %s" % (name, val))
            if name == "zooms":
                if val is not None:
                    for i in val:
                        if int(i) < 14 or int(i) > 18:
                            print("%r out of zoom range" % i)
                            self.usage()
            if name == "source":
                srcs = val.split(',')
                for i in srcs:
                    if i == "ersi" or i == "topo" or i == "terrain" or i == "usgs":
                        self.options[i] = True
                        continue
                    else:
                        print("%r unsupported source" % i)
                        self.usage()
            if name == "format":
                fmts = val.split(',')
                for i in fmts:
                    if i == "gtiff" or i == "pdf" or i == "osmand":
                        self.options[i] = True
                        continue
                    else:
                        print("%r unsupported format" % i)
                        self.usage()

    def get(self, opt):
        try:
            return self.options[opt]
        except Exception as inst:
            return False

    def dump(self):
        logging.info("Dumping config")
        for i, j in self.options.items():
            print("\t%s: %s" % (i, j))

    # Basic help message
    def usage(self, argv=["tiler.py"]):
        print("This program downloads map tiles and the geo-references them")
        print(argv[0] + ": options:")
        print("""\t--help(-h)   Help
\t--outdir(-o)    Output directory for tiles
\t--source(-s)    Map source (default, usgs)
                  ie... topo,terrain,ersi,usgs
\t--poly(-p)      Input OSM polyfile
\t--format(-f)    Output file format,
                  ie... GTiff, PDF, AQM, OSMAND
\t--zooms(-z)     Zoom levels to download (14-18)
\t--nodata(-n)    Disable downloading OSM data
\t--download(-d)  Download map tiles
\t--verbose(-v)   Enable verbosity
        """)
        quit()

dd = myconfig(argv)
dd.checkOptions()
#dd.dump()
if len(argv) <= 2:
    dd.usage(argv)

# The logfile contains multiple runs, so add a useful delimiter
try:
    logging.info("-----------------------\nStarting: %r " % argv)
except:
    pass

# if verbose, dump to the terminal as well as the logfile.
if dd.get('verbose') == 1:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)

outfile = dd.get('outfile')
mod = 'action="modifiy"'

poly = Poly()
bbox = poly.getBBox(dd.get('poly'))
#logging.info("Bounding box is %r" % bbox)

# XAPI uses:
# minimum latitude, minimum longitude, maximum latitude, maximum longitude
xbox = "%s,%s,%s,%s" % (bbox[2], bbox[0], bbox[3], bbox[1])
#logging.info("Bounding xbox is %r" % xbox)

print("------------------------")
#xapi = "(\n  way(%s);\n  node(%s);\n  rel(%s);\n  <;\n  >;\n);\nout meta;" % (box , xbox, xbox)
#print(xapi)
# osmc.createChanges()
# osmc.applyChanges()

#xapi = '[adiff: "2018-03-29T00:26:13Z","2019-05-13T17:27:18-06:00"];' + xapi

# Download data from OpenStreetMap
if dd.get('nodata') is False:
    logging.info("Downloading OSM data, which could take awhile...")
    xapi = "(way(%s);node(%s);rel(%s);<;>;);out meta;" % (xbox, xbox, xbox)
    polyfile = dd.get('poly')
    polyname = os.path.basename(polyfile.replace(".poly", ""))

    now = datetime.now().isoformat()

    osmc = osmConvert()
    last = osmc.getLastTimestamp(outfile + '/' + polyname + ".osm")
    if last is not None:
        tdelta = timedelta(seconds=10)
        past = last + tdelta
        logging.info("Last timestamp in %s is %s" % (polyname + ".osm", past.isoformat()))
        xapi = '[adiff: "%s","%s"];%s' % (past.isoformat(), now, xapi)

    logging.debug("XAPI: %s" % xapi)
    uri = 'https://overpass-api.de/api/interpreter'
    #uri = 'https://overpass-api.de/api/augmented_diff'
    headers = dict()
    headers['Content-Type'] = 'application/x-www-form-urlencodebd'
    req = urllib.request.Request(uri, headers=headers)
    x = urllib.request.urlopen(req, data=xapi.encode('utf-8'))
    output = x.read().decode('utf-8')
    #logging.debug("FIXME: %r" % len(output))
    adiff = "interpreter"
    if last is not None:
        osmfile = open(adiff, 'w')
    else:
        osmfile = open(outfile + '/' + polyname + '.osm', 'w')
    osmfile.write(output)
    osmfile.close()

    # Make changeset file
    if last is not None and len(output) > 300:
        o5m = osmc.createChanges(adiff)
        osmc.applyChanges(polyname + ".osm")
    else:
        logging.info("No changes found for %s" % polyname + '.osm')

if dd.get('download') is False and dd.get('download') is False:
    logging.info("Not downloading anything (the default)")
    quit()

# https://mt.google.com/vt/lyrs=s&x=${X}&amp;y=${y}&z=${Z} -- Satellite
# https://mt.google.com/vt/lyrs=y&amp;x=${X}&amp;y=${y}&z=${Z} -- Hybrid
# https://mt.google.com/vt/lyrs=t&amp;x=${X}&amp;y=${y}&z=${Z} -- Terrain 
# https://mt.google.com/vt/lyrs=p&amp;x=${X}&amp;y=${y}&z=${Z} -- Terrain, Streets and Water

# (-105.689729, -105.408747, 39.932244, 40.021688)
# https://a.tile.opentopomap.org/13/1696/3102.png
# https://basemap.nationalmap.gov/ArcGIS/rest/services/USGSTopo/MapServer/tile/13/3102/1696
# http://mt0.google.com/vt/lyrs=h&x=1696&y=3102&z=13&scale=1

# <customMapSource>
#    <name>Google-hybrid-256</name>
#    <minZoom>0</minZoom>
#    <maxZoom>19</maxZoom>
#    <tileType>png</tileType>
#    <tileUpdate>None</tileUpdate>
#    <url>http://mt{$serverpart}.google.com/vt/lyrs=h&amp;x={$x}&amp;y={$y}&amp;z={$z}&amp;scale=1</url>
#    <serverParts>0 1 2 3</serverParts>
#  </customMapSource>

usgsdb = Tiledb(outfile + "/USGS")
topodb = Tiledb(outfile + "/Topo")
terraindb = Tiledb(outfile + "/Terrain")
#hybridb = Tiledb(outfile + "/Hybrid")
ersidb = Tiledb(outfile + "/ERSI")


# mappacks/region_america_north/USNationalMapRelief.java
# https://basemap.nationalmap.gov/ArcGIS/rest/services/USGSTopo/MapServer/tile/Z/Y/X
# https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/Z/Y/X
# https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/Z/Y/X
# We only need to download the largest zoom level, and use
# 'gdaladdo -r nearest foo.tif 2 4 8 16 32 64 128 256 512 1024'
# to generate the lower resolution zoom levels as layers.


path = dd.get('poly').split('.')
dbfile = outfile + "/tiledb"

if dd.get('usgs'):
    zoom = 15
    #zoom =  tuple(dd.get('zooms'))
    logging.debug("Zoom level for USGS is: %r" % str(zoom))
    tiles = list(mercantile.tiles(bbox[0], bbox[2], bbox[1], bbox[3], zoom))
    if dd.get('download'):
        # tile/Z/Y/X
        url = "https://basemap.nationalmap.gov/ArcGIS/rest/services/USGSTopo/MapServer/tile/{0}/{2}/{1}"
        mirrors = [url]
        if usgsdb.download(mirrors, tiles):
            logging.info("Done downloading USGS data")
    filespec = outfile + '/' + os.path.basename(path[0]) + '-USGS' + str(zoom) + '.txt'
    usgsdb.writeCache(tiles, filespec)
    usgsdb.writeDB(tiles, dbfile, poly.getName(), 'usgs')


if dd.get('topo'):
    # tiles = list(mercantile.tiles(bbox[0], bbox[2], bbox[1], bbox[3], dd.get('zooms')))
    zoom = 15
    #zoom =  tuple(dd.get('zooms'))
    logging.debug("Zoom level for topos is: %r" % str(zoom))
    tiles = list(mercantile.tiles(bbox[0], bbox[2], bbox[1], bbox[3], zoom))
    if dd.get('download') and dd.get('topo'):
        # (OpenTopo uses Z/X/Y.png format
        url = ".tile.opentopomap.org/{0}/{1}/{2}.png"
        mirrors = [ "https://a" + url, "https://b" + url, "https://c" + url ]
        if topodb.download(mirrors, tiles):
            logging.info("Done downloading Topo data")
    filespec = outfile + '/' + os.path.basename(path[0]) + '-Topo' + str(zoom) + '.txt'
    topodb.writeCache(tiles, filespec)
    topodb.writeDB(tiles, dbfile, poly.getName(), 'topo')
#if dd.get('mosaic') is True and dd.get('topo'):
#    topodb.mosaic(tiles)

# Sat Imagery
if dd.get('ersi'):
    zoom = 16
    tiles = list(mercantile.tiles(bbox[0], bbox[2], bbox[1], bbox[3], zoom))
    if dd.get('download'):
        # Zooms seems to go to 19, 18 was huge, and 17 was fine
        logging.debug("Zoom level for ERSI is: %r" % str(zoom))
        url = "http://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{0}/{2}/{1}"
        mirrors = [url]
        if ersidb.download(mirrors, tiles):
            logging.info("Done downloading Sat imagery")
    filespec = path[0] + '-Sat' + str(zoom) + '.txt'
    ersidb.writeCache(tiles, filespec)
    ersidb.writeDB(tiles, dbfile, poly.getName(), 'ersi')

#if dd.get('mosaic') is True and dd.get('ersi'):
#    ersidb.mosaic(tiles)

# 17 appears to be the max zoom level available
if dd.get('terrain'):
    zoom = 16
    logging.debug("Zoom level for Terrain is: %r" % str(zoom))
    tiles = list(mercantile.tiles(bbox[0], bbox[2], bbox[1], bbox[3], zoom))
    url = "http://caltopo.s3.amazonaws.com/topo/{2}/{1}/{0}.png"
    mirrors = [url]
    if dd.get('download'):
        if terraindb.download(mirrors, tiles):
            logging.info("Done downloading Topo data")
            terraindb.writeCache(tiles,filespec)
    filespec = path[0] + '-Terrain' + str(zoom) + '.txt'
    usgsdb.writeDB(tiles, dbfile, poly.getName(), 'terrain')
#if dd.get('mosaic') is True and dd.get('terrain'):
#    terraindb.mosaic(tiles)

    
#url = ".google.com/vt/lyrs=h&x=$X&y=$Y&z=$Z&scale=1" % (tile.x, tile.y, tile.z)
#mirrors = [ "https://mt0" + url, "https://mt1" + url, "https://mt2" + url ]
#print("lynx " + url + '\n')
#hybridb.download(mirrors)

# # lat increases northward, 0 - 90
# # lon increases eastward, 0 - 180 

# This creates 3 lower zoom levels, used for datavase driven
# mapping formats like Osmand sqlitedb or mbtiles formats.
ersidb.makeLevels()
