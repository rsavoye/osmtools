# 
# Copyright (C) 2017, 2018, 2019, 2020   Free Software Foundation, Inc.
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

import sys
import os.path
import time
import logging
from datafile import convfile
import config
import html
import string
import re
import epdb
from subprocess import PIPE, Popen, STDOUT
import subprocess
ON_POSIX = 'posix' in sys.builtin_module_names
from datetime import datetime
import correct
import overpass
from poly import Poly


class osmfile(object):
    """OSM File output"""
    def __init__(self, options, filespec=None):
        self.options = options
        # Read the config file to get our OSM credentials, if we have any
        # self.config = config.config(self.options)
        self.version = 3
        self.visible = 'true'
        self.osmid = -30470
        # Open the OSM output file
        if filespec is None:
            self.file = self.options.get('outdir') + "foobar.osm"
        else:
            self.file = open(filespec, 'w')
            # self.file = open(filespec + ".osm", 'w')
        logging.info("Opened output file: " + filespec )
        #logging.error("Couldn't open %s for writing!" % filespec)

        # This is the file that contains all the filtering data
        self.ctable = convfile(options.get('convfile'))
        # These are for importing the CO addresses
        self.full = None
        self.addr = None

    def isclosed(self):
        return self.file.closed

    def header(self):
        if self.file is not False:
            self.file.write('<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n')
            #self.file.write('<osm version="0.6" generator="gosm 0.1" timestamp="2017-03-13T21:43:02Z">\n')
            self.file.write('<osm version="0.6" generator="gosm 0.1">\n')

    def footer(self):
        #logging.debug("FIXME: %r" % self.file)
        self.file.write("</osm>\n")
        if self.file != False:
            self.file.close()

    def writeWay(self, way=list()):
        for line in way:
            self.file.write("%s\n" % line)

    def mergeTags(self, tags1, tags2):
        """Merge two sets of tags together. This would be easy if all the
        values matched exactly, but often imported datra sucks... so
        apply some fuzzy logic to the merge, or mark it for later review in JOSM.
        """
        filter = ['osm_id', 'lat', 'lon']
        newtags = dict()
        for key, value in tags1.items():
            if key == 'osm_id' or key == 'lat' or key == 'lon' or value == 'None':
                continue
            if key in tags2:  # see if there is a duplicate tag
                if tags1[key] == tags2[key] and value != 'None':
                    newtags[key] = value
                else:
                    newtags['alt_' + key] = tags2[key]
        for key, value in tags2.items():
            if key == 'osm_id' or key == 'lat' or key == 'lon' or value == 'None':
                continue
            if key in newtags is False and value != 'None':
                newtags[key] = value
                        
        return newtags

    def writeNode(self, tags=list(), attrs=dict(), modified=False):
        #        timestamp = ""  # LastUpdate
        timestamp = datetime.now().strftime("%Y-%m-%dT%TZ")
        # self.file.write("       <node id='" + str(self.osmid) + "\' visible='true'")
        try:
            x = attrs['osmid']
        except:
            try:
                x = attrs['id']
            except:
                attrs['id'] = str(self.osmid)
                self.osmid -= 1

        if 'user' in attrs:
            try:
                x = str(attrs['user'])
            except:
                attrs['user'] = str(self.options.get('user'))
        if 'uid' in attrs:
            try:
                x = str(attrs['uid'])
            except:
                attrs['uid'] = str(self.options.get('uid'))

        if len(attrs) > 0:
            self.file.write("    <node")
            for ref,value in attrs.items():
                self.file.write(" " + ref + "=\"" + value + "\"")
            if len(tags) > 0:
                self.file.write(">\n")
            else:
                self.file.write("/>\n")

        for i in tags:
            for name, value in i.items():
                if name == "Ignore" or value == None:
                    continue
                if str(value)[0] != 'b':
                    if value != 'None' or value != 'Ignore':
                        tag = self.makeTag(name, value)
                        for newname, newvalue in tag.items():
                            # if newname == 'addr:street' or newname == 'addr:full' or newname == 'name' or newname == 'alt_name':
                            #     newvalue = string.capwords(newvalue)
                            self.file.write("    <tag k=\"" + newname + "\" v=\"" + str(newvalue) + "\"/>\n")

        if len(tags) > 0:
            self.file.write("    </node>\n")

        return self.osmid

    # Here's where the fun starts. Read a field header from a file,
    # which of course are all different. Make an attempt to match these
    # random field names to standard OSM tag names. Same for the values,
    # which for OSM often have defined ranges.
    def makeTag(self, field, value):
        fix = correct.correct()
        newval = str(value)
        #newval = html.unescape(newval)
        newval = newval.replace('&', 'and')
        newval = newval.replace('"', '')
        #newval = newval.replace('><', '')
        tag = dict()
        # logging.debug("OSM:makeTag(field=%r, value=%r)" % (field, newval))

        try:
            newtag = self.ctable.match(field)
        except Exception as inst:
            logging.warning("MISSING Field: %r, %r" % (field, newval))
            # If it's not in the conversion file, assume it maps directly
            # to an official OSM tag.
            newtag = field


        newval = self.ctable.attribute(newtag, newval)
        #logging.debug("ATTRS1: %r %r" % (newtag, newval))
        change = newval.split('=')
        if len(change) > 1:
            newtag = change[0]
            newval = change[1]

        # name tags, usually roads or addresses, often have to be tweaked
        # for OSM standards
        if (newtag == "name") or (newtag == "alt_name"):
            newval = string.capwords(fix.alphaNumeric(newval))
            newval = fix.abbreviation(newval)
            newval = fix.compass(newval)

        # This is a hack because the CO address data truncates the street,
        # and we need the whole thing so routing will work to an address.
        if newtag == 'addr:full':
            self.full = re.sub(" Unit .*", '', newval)
            newval = re.sub("^[0-9]* ", '', self.full)
            newtag = "add:street"
            # logging.debug("FIXME: FULL %" % self.full)
        elif newtag == 'addr:housenumber':
            # logging.debug("FIXME: NUM")
            self.num = newval
        elif newtag == 'addr:street':
            if self.full is not None:
                newval = re.sub("^[0-9]* ", '', self.full)
                # newval = self.full.replace(self.num, '')

        self.full = None
        self.addr = None
        tag[newtag] = newval
        # tag[newtag] = string.capwords(newval)

        #print("ATTRS2: %r %r" % (newtag, newval))
        return tag

    def makeWay(self, refs, tags=list(), attrs=dict(), modified=True):
        if len(refs) is 0:
            logging.error("No refs! %r" % tags)
            return

        if len(attrs) > 0:
            self.file.write("  <way")
            for ref,value in attrs.items():
                self.file.write("    " + ref + "=\"" + value + "\"")
            self.file.write(">\n")
        else:
            #try:
            #    x = attrs['osmid']
            #except:
            #    attrs['id'] = str(self.osmid)

            #logging.debug("osmfile::way(refs=%r, tags=%r)" % (refs, tags))
            #logging.debug("osmfile::way(tags=%r)" % (tags))
            self.file.write("    <way")
            timestamp = datetime.now().strftime("%Y-%m-%dT%TZ")

            if modified:
                self.file.write(" action='modified'")
            self.file.write(" version='1'")
            self.file.write(" id=\'" + str(self.osmid) + "\'")
            self.file.write(" timestamp='" + timestamp + "\'>\n")
#            self.file.write(" user='" + self.options.get('user') + "' uid='" +
#                            str(self.options.get('uid')) + "'>'\n")

        # Each ref ID points to a node id. The coordinates is im the node.
        for ref in refs:
            # FIXME: Ignore any refs that point to ourself. There shouldn't be
            # any, so this is likely a bug elsewhere when parsing the geom.
            # logging.debug("osmfile::way(ref=%r, osmid=%r)" % (ref, self.osmid))
            if ref == self.osmid:
                break
            self.file.write("    <nd ref=\"" + str(ref) + "\"/>\n")

        value = ""

        for i in tags:
            for name, value in i.items():
                if name == "Ignore" or value == '':
                    continue
                if str(value)[0] != 'b':
                    self.file.write("    <tag k=\"" + name + "\" v=\"" +
                                    str(value) + "\"/>\n")

        self.file.write("  </way>\n")
        self.osmid = int(self.osmid) - 1

    def makeRelation(self, members, tags=list(), attrs=dict()):
        if len(attrs) > 0:
            self.file.write("  <relation")
            for ref,value in attrs.items():
                self.file.write(" " + ref + "=\"" + value + "\"")
            self.file.write(">\n")

        # Each ref ID points to a node id. The coordinates is im the node.
        for mattr in members:
            for ref, value in mattr.items():
                #print("FIXME: %r %r" % (ref, value))
                if ref == 'type':
                    self.file.write("    <member")
                self.file.write(" " + ref + "=\"" + value + "\"")
                if ref == 'role':
                    self.file.write("/>\n")

        value = ""

        for i in tags:
            for name, value in i.items():
                if name == "Ignore" or value == '':
                    continue
                if str(value)[0] != 'b':
                    self.file.write("    <tag k=\"" + name + "\" v=\"" + str(value) + "\"/>\n")
            
        self.file.write("  </relation>\n")

    def cleanup(self, tags):
        cache = dict()
        for tag in tags:
            for name, value in tag.items():
                try:
                    if cache[name] != value:
                        tmp = cache[name]
                        cache[name] += ';' + value
                except:
                    cache[name] = value

        tags = list()
        tags.append(cache)
        return tags


class osmConvert(object):
    def __init__(self, file=None):
        """This class uses osmconvert to apply a changeset to an OSM file"""
        self.file = file
        # Make changeset file
        # osmconvert interpreter --out-o5m -o=interpreter.o5m
        # osmconvert previous.osm interpreter.o5m -o now.osm

    def getLastTimestamp(self, file=None):
        """First find the last timestamp in the OSM file so we know where
        to start the adiff."""

        if file is None and self.file is not None:
            file = self.file

        if os.path.exists(file) is False:
            logging.warning("%s does not exist!" % file)
            return None
        else:
            if os.stat(file).st_size == 0:
                logging.error("%s has zero content!" % file)
                return None

        cmd = "grep -o 'timestamp=.[0-9A-Z:-]*'" + " " + file + " | sort -M | tail -1"
        grep = subprocess.check_output(cmd, shell=True)
        if len(grep) == 0:
            logging.error("Couldn't get last timestamp from %s!" % file)
            return None
        # Clean up the timestamp and make it a datetime type
        timestamp = grep.decode('utf-8').split('=')[1].strip('\n\"Z')
        return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')

    def createChanges(self, adiff=None):
        """This method takes an adiff file as produced by the Overpass QL
        server, which then later gets applied to produce an updated OSM file."""
        if adiff is None and self.file is not None:
            adiff = self.file

        if os.path.exists(adiff) is False:
            logging.error("%s doesn't exist!" % adiff)
            return None

        outfile = "/tmp/osmc" + str(os.getpid()) + '.o5m'
        cmd = "osmconvert " + adiff + " --out-o5m -o=" + outfile
        diff = subprocess.check_output(cmd, shell=True)
        if len(diff) == 0:
            return outfile

    def applyChanges(self, file=None):
        """Apply the chngeset file to the osm file"""
        if file is None and self.file is not None:
            file = self.file

        if os.path.exists(file) is False:
            logging.error("%s doesn't exist!" % file)
            return False

        os.rename(file, "tmp.osm")
        adiff = "/tmp/osmc" + str(os.getpid()) + '.o5m'
        cmd = 'osmconvert ' + "tmp.osm " + adiff + ' -o=' + file
        osmc = subprocess.check_output(cmd, shell=True)

        return True

    def applyPoly(self, poly, infile, outfile):
        """This method use an OSM poly file to produce a subset
        from a larger dataset
        """
        if os.path.exists(poly) is False:
            logging.error("%s doesn't exist!" % adiff)
            return None

        cmd = ["osmconvert", "-B=" + poly, "-o=" + outfile, "--max-refs=400000", "--drop-broken-refs", "--complete-ways", infile]
        ppp = Popen(cmd, stdout=PIPE, bufsize=0, close_fds=ON_POSIX)
        ppp.wait()

        logging.info("Produced %s from %s using %s" % (outfile, infile, poly))


# If we trigger too many requests from the same IP, it can be reset like this:
# http://overpass-api.de/api/kill_my_queries
# At the same time, the server is a shared resource, so be polite and only
# do this during debugging.
class OverpassXAPI(object):
    """Get data from OSM using the Overpass API"""
    def __init__(self, bbox=None, filespec=None):
        self.filespec = filespec
        self.bbox = bbox

    def getData(self, filespec=None):
        logging.info("Downloading data using Overpass")
        api = overpass.API(timeout=600, debug=True)
        query = overpass.MapQuery(self.bbox[2], self.bbox[0], self.bbox[3], self.bbox[1])
        try:
            response = api.get(query, responseformat="xml")
        except:
            logging.error("Overpass query failed! Sometimes the server is overloaded")
            return False

        if filespec is None and self.filespec is None:
            outfile = open('out.osm', 'w')
        elif filespec is None and self.filespec is not None:
            outfile = open(self.filespec, 'w')
        else:
            outfile = open(filespec, 'w')

        logging.info("Writing OSM data to %s" % self.filespec)
        outfile.write(response)
        outfile.close()
        return True
